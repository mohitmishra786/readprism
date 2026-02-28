from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def send_email_sync(
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    reply_to: str | None = None,
) -> bool:
    """
    Send an email via Zoho SMTP (synchronous).
    Called from async code via asyncio.to_thread() to avoid blocking the event loop.
    """
    settings = get_settings()

    if not settings.zoho_password:
        logger.warning("ZOHO_PASSWORD not configured — email not sent")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"ReadPrism <{settings.zoho_email}>"
        msg["To"] = to
        if reply_to:
            msg["Reply-To"] = reply_to

        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(settings.zoho_smtp_host, settings.zoho_smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.zoho_email, settings.zoho_password)
            server.sendmail(settings.zoho_email, to, msg.as_string())

        logger.info(f"Email sent to {to} via Zoho SMTP (subject={subject!r})")
        return True

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"Zoho SMTP authentication failed: {e}")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"Zoho SMTP error sending to {to}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending email to {to}: {e}")
        return False


async def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
    reply_to: str | None = None,
) -> bool:
    """
    Async wrapper — runs the blocking SMTP call in a thread pool so the event
    loop is never blocked.
    """
    import asyncio
    return await asyncio.to_thread(
        send_email_sync, to, subject, html_body, text_body, reply_to
    )
