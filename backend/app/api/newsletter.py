from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.services.ingestion.newsletter import (
    ensure_newsletter_source,
    process_inbound_email,
    verify_mailgun_signature,
)
from app.utils.cache import CacheUnavailable, cache_set_nx_strict
from app.utils.logging import get_logger

router = APIRouter(prefix="/newsletter", tags=["newsletter"])
logger = get_logger(__name__)
settings = get_settings()


async def _first_seen(key: str) -> bool:
    """Replay guard that fails closed (#156): with Redis down we cannot tell a
    replay from a first delivery, so answer 503 and let the provider retry."""
    try:
        return await cache_set_nx_strict(
            key, "1", ttl_seconds=settings.newsletter_webhook_max_age_seconds
        )
    except CacheUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Temporarily unavailable",
            headers={"Retry-After": "60"},
        )


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


async def _remember_sender(
    session: AsyncSession,
    user_id_str: str | None,
    sender: str,
    *,
    list_unsubscribe: str | None = None,
    header_to: str | None = None,
) -> None:
    if not user_id_str:
        return
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        return
    await ensure_newsletter_source(
        session, user_id, sender, list_unsubscribe=list_unsubscribe, header_to=header_to
    )


def _mailgun_header(source, name: str) -> str | None:
    """A header from Mailgun's 'message-headers' ([[name, value], ...])."""
    import json

    if source is None:
        return None
    raw = source.get("message-headers")
    try:
        pairs = json.loads(raw) if isinstance(raw, str) else raw or []
    except ValueError:
        return None
    for pair in pairs if isinstance(pairs, list) else []:
        if isinstance(pair, list) and len(pair) == 2 and str(pair[0]).lower() == name.lower():
            return str(pair[1])
    return None


@router.post("/inbound", status_code=status.HTTP_200_OK)
async def inbound_email(request: Request, session: AsyncSession = Depends(get_db)) -> dict:
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
            raw = await request.json()
            if not isinstance(raw, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload"
                )
            payload = raw
            sender = raw.get("sender") or raw.get("from", "")
            subject = raw.get("subject", "Newsletter")
            body_text = raw.get("body-plain") or raw.get("body", "")
            message_id = raw.get("Message-Id") or raw.get("message_id", "")
            recipient = raw.get("recipient") or raw.get("to", "")
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
        first_seen = await _first_seen(f"mailgun:webhook:token:{token}")
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
        else:
            # The personal address shown in the app: u.<token>@domain (#151).
            from app.services.ingestion.newsletter_parse import recipient_token

            address_token = recipient_token(recipient)
            if address_token:
                found = await session.execute(
                    select(User.id).where(User.newsletter_token == address_token)
                )
                owner_id = found.scalar_one_or_none()
                user_id_str = str(owner_id) if owner_id else None

    from app.services.email_verification import may_receive_newsletters

    if not await may_receive_newsletters(session, user_id_str):
        return {"status": "ignored", "reason": "recipient has not verified their email"}
    from app.services.abuse import inbound_allowed

    allowed, why = await inbound_allowed(user_id_str, len(body_text.encode()))
    if not allowed:
        logger.warning(f"Inbound newsletter dropped: {why}")
        return {"status": "ignored", "reason": why}
    if user_id_str:
        allowed, why = await _plan_allows_newsletter(session, user_id_str, len(body_text.encode()))
        if not allowed:
            logger.info(f"Inbound newsletter dropped: {why}")
            return {"status": "ignored", "reason": why}
    from app.services.newsletter_address import record_if_test

    if await record_if_test(user_id_str, subject):
        return {"status": "test_received"}

    await process_inbound_email(
        sender=sender,
        subject=subject,
        body=body_text,
        message_id=message_id,
        user_id=user_id_str,
    )
    fields = payload if payload is not None else form
    await _remember_sender(
        session,
        user_id_str,
        sender,
        list_unsubscribe=_mailgun_header(fields, "List-Unsubscribe"),
        header_to=str((fields or {}).get("To") or _mailgun_header(fields, "To") or recipient),
    )

    return {"status": "ok"}


@router.post("/inbound/{provider}", status_code=status.HTTP_200_OK)
async def inbound_provider(
    provider: str, request: Request, session: AsyncSession = Depends(get_db)
) -> dict:
    """Postmark, Resend, and Cloudflare Email webhooks. IMAP uses parse_rfc822 directly.

    Each provider signs the raw body with HMAC-SHA256. Outside development an
    empty secret rejects the call. A repeated message id is a replay.
    """
    import json

    from app.services.ingestion.newsletter_parse import (
        parse_cloudflare,
        parse_postmark,
        parse_resend,
        verify_body_hmac,
    )

    parsers = {
        "postmark": (settings.postmark_webhook_secret, parse_postmark),
        "resend": (settings.resend_webhook_secret, parse_resend),
        "cloudflare": (settings.cloudflare_email_webhook_secret, parse_cloudflare),
    }
    if provider not in parsers:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown provider")
    secret, parser = parsers[provider]
    raw = await request.body()
    signature = (
        request.headers.get("x-webhook-signature")
        or request.headers.get("x-postmark-signature")
        or ""
    )
    if not secret:
        if settings.app_env != "development":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook not authenticated"
            )
    elif not verify_body_hmac(secret=secret, payload=raw, signature=signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    parsed = parser(payload)
    first_seen = await _first_seen(f"newsletter:webhook:{provider}:{parsed.dedupe_key}")
    if not first_seen:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate webhook")
    from app.services.ingestion.newsletter_parse import recipient_token

    token = recipient_token(parsed.recipient)
    owner = None
    if token:
        found = await session.execute(select(User.id).where(User.newsletter_token == token))
        owner = found.scalar_one_or_none()
    from app.services.email_verification import may_receive_newsletters

    if owner and not await may_receive_newsletters(session, owner):
        return {"status": "ignored", "reason": "recipient has not verified their email"}
    from app.services.abuse import inbound_allowed

    allowed, why = await inbound_allowed(owner, len(raw))
    if not allowed:
        logger.warning(f"Inbound newsletter dropped: {why}")
        return {"status": "ignored", "reason": why}
    if owner:
        allowed, why = await _plan_allows_newsletter(session, owner, len(raw))
        if not allowed:
            logger.info(f"Inbound newsletter dropped: {why}")
            return {"status": "ignored", "reason": why}
    from app.services.newsletter_address import record_if_test

    if await record_if_test(owner, parsed.subject):
        return {"status": "test_received"}
    await process_inbound_email(
        sender=parsed.sender,
        subject=parsed.subject,
        body=parsed.text,
        message_id=parsed.message_id,
        user_id=str(owner) if owner else None,
    )
    if owner:
        await ensure_newsletter_source(
            session,
            owner,
            parsed.sender,
            list_unsubscribe=parsed.list_unsubscribe,
            header_to=parsed.header_to,
        )
    return {
        "status": "ok",
        "confirmation": parsed.is_confirmation,
        "list_unsubscribe": parsed.list_unsubscribe,
        "view_in_browser": parsed.view_in_browser,
    }


# ---------------------------------------------------------------- your address


@router.get("/address")
async def my_newsletter_address(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """The user's personal inbound address, created on first use (#151)."""
    from app.services import newsletter_address as na
    from app.services.email_verification import is_verified

    token = await na.ensure_token(current_user, session)
    return {
        "address": na.address_for(token),
        "inbound_configured": na.inbound_configured(),
        "email_verified": is_verified(current_user),
    }


@router.post("/address/test", status_code=status.HTTP_202_ACCEPTED)
async def send_address_test(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Mail a marker to the user's address; poll GET /address/test to see it arrive."""
    from app.services import newsletter_address as na
    from app.utils.cache import cache_set_nx
    from app.utils.email import send_email

    if not na.inbound_configured():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Inbound newsletters are not set up on this instance yet.",
        )
    if not await cache_set_nx(f"newsletter-test-sent:{current_user.id}", 1, ttl_seconds=60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="One test a minute, please."
        )
    token = await na.ensure_token(current_user, session)
    nonce = await na.start_test(current_user.id)
    sent = await send_email(
        to=na.address_for(token),
        subject=f"{na.TEST_SUBJECT_PREFIX}{nonce}",
        html_body="<p>This is a Weirling test of your newsletter address.</p>",
    )
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Couldn't send the test email (check SMTP settings).",
        )
    return {"status": "sent"}


@router.get("/address/test")
async def address_test_status(current_user: User = Depends(get_current_user)) -> dict:
    from app.services.newsletter_address import test_status

    return await test_status(current_user.id)


async def _plan_allows_newsletter(session, user_id, size_bytes: int) -> tuple[bool, str]:
    """The recipient's plan quota for newsletters (#172); always allowed off hosted."""
    from app.services import entitlements

    if not entitlements.is_hosted():
        return True, ""
    user = await session.get(User, uuid.UUID(str(user_id)))
    if user is None:
        return True, ""
    return await entitlements.newsletter_allowed(user, size_bytes)
