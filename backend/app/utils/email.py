from __future__ import annotations

import httpx

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
) -> bool:
    if settings.email_provider == "resend":
        return await _send_via_resend(to, subject, html_body, text_body)
    else:
        logger.warning(f"Unknown email provider: {settings.email_provider}")
        return False


async def _send_via_resend(
    to: str, subject: str, html_body: str, text_body: str | None
) -> bool:
    if not settings.resend_api_key:
        logger.warning("RESEND_API_KEY not configured — email not sent")
        return False

    payload: dict = {
        "from": settings.from_email,
        "to": [to],
        "subject": subject,
        "html": html_body,
    }
    if text_body:
        payload["text"] = text_body

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            logger.info(f"Email sent to {to} via Resend (id={resp.json().get('id')})")
            return True
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return False
