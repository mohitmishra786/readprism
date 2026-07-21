from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.config import get_settings
from app.services.ingestion.newsletter import (
    process_inbound_email,
    verify_mailgun_signature,
)
from app.utils.cache import cache_set_nx
from app.utils.logging import get_logger

router = APIRouter(prefix="/newsletter", tags=["newsletter"])
logger = get_logger(__name__)
settings = get_settings()


def _extract_signature_fields(
    content_type: str, payload: dict | None, form
) -> tuple[str, str, str]:
    """Pull (token, timestamp, signature) from a Mailgun payload.

    Inbound-route (form) posts carry them at the top level; the newer JSON
    webhook format nests them under a `signature` object.
    """
    if "application/json" in content_type and payload is not None:
        sig = payload.get("signature")
        if isinstance(sig, dict):
            return (
                str(sig.get("token", "")),
                str(sig.get("timestamp", "")),
                str(sig.get("signature", "")),
            )
        return (
            str(payload.get("token", "")),
            str(payload.get("timestamp", "")),
            str(payload.get("signature", "")),
        )
    if form is not None:
        return (
            str(form.get("token", "")),
            str(form.get("timestamp", "")),
            str(form.get("signature", "")),
        )
    return "", "", ""


@router.post("/inbound", status_code=status.HTTP_200_OK)
async def inbound_email(request: Request) -> dict:
    """
    Webhook endpoint for inbound newsletter emails from Mailgun.

    **Authenticated**: every post must carry a valid Mailgun signature
    (HMAC-SHA256 of timestamp+token with the Webhook Signing Key). Without a
    configured signing key the endpoint is fail-closed outside development, so
    it can never ship as an open content-injection door (audit 06-1).
    """
    content_type = request.headers.get("content-type", "")
    payload: dict | None = None
    form = None
    try:
        if "application/json" in content_type:
            payload = await request.json()
            sender = payload.get("sender") or payload.get("from", "")
            subject = payload.get("subject", "Newsletter")
            body_text = payload.get("body-plain") or payload.get("body", "")
            message_id = payload.get("Message-Id") or payload.get("message_id", "")
            recipient = payload.get("recipient") or payload.get("to", "")
        else:
            form = await request.form()
            sender = str(form.get("sender") or form.get("from", ""))
            subject = str(form.get("subject", "Newsletter"))
            body_text = str(form.get("body-plain") or form.get("body", ""))
            message_id = str(form.get("Message-Id") or form.get("message_id", ""))
            recipient = str(form.get("recipient") or form.get("to", ""))
    except Exception as e:
        logger.error(f"Failed to parse inbound email payload: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")

    # --- Authentication: verify the Mailgun signature ---------------------
    token, timestamp, signature = _extract_signature_fields(content_type, payload, form)
    signing_key = settings.mailgun_webhook_signing_key

    if not signing_key:
        if settings.app_env == "development":
            logger.warning(
                "MAILGUN_WEBHOOK_SIGNING_KEY is unset — accepting inbound webhook "
                "WITHOUT verification (development only). Set it before deploying."
            )
        else:
            logger.error(
                "MAILGUN_WEBHOOK_SIGNING_KEY is unset in a non-development env; "
                "rejecting inbound webhook (fail-closed)."
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook not authenticated"
            )
    else:
        if not verify_mailgun_signature(
            token=token,
            timestamp=timestamp,
            signature=signature,
            signing_key=signing_key,
            max_age_seconds=settings.newsletter_webhook_max_age_seconds,
        ):
            logger.warning("Rejected inbound webhook: invalid or stale Mailgun signature")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature"
            )
        # Replay guard: a valid signature can be captured and resent within the
        # freshness window; refuse a token we've already honoured.
        first_seen = await cache_set_nx(
            f"mailgun:webhook:token:{token}",
            "1",
            ttl_seconds=settings.newsletter_webhook_max_age_seconds,
        )
        if not first_seen:
            logger.warning("Rejected inbound webhook: replayed Mailgun token")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate webhook")

    if not body_text:
        return {"status": "ignored", "reason": "empty body"}

    # Extract user_id from recipient address (format: user-{uuid}@newsletter.domain)
    user_id_str: str | None = None
    if recipient:
        local_part = recipient.split("@")[0]
        if local_part.startswith("user-"):
            user_id_str = local_part[5:]

    await process_inbound_email(
        sender=sender,
        subject=subject,
        body=body_text,
        message_id=message_id,
        user_id=user_id_str,
    )

    return {"status": "ok"}
