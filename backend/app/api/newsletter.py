from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request, status

from app.services.ingestion.newsletter import process_inbound_email
from app.utils.cache import get_redis
from app.utils.logging import get_logger

router = APIRouter(prefix="/newsletter", tags=["newsletter"])
logger = get_logger(__name__)


@router.post("/inbound", status_code=status.HTTP_200_OK)
async def inbound_email(request: Request) -> dict:
    """
    Webhook endpoint for inbound newsletter emails from Mailgun or similar providers.
    Mailgun posts multipart/form-data; we accept both form and JSON.
    """
    content_type = request.headers.get("content-type", "")
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
