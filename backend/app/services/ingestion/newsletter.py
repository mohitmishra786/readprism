from __future__ import annotations

import email as email_lib
import uuid
from typing import Optional

from app.services.ingestion.rss_parser import RawContentItem
from app.utils.cache import cache_set
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _html_to_text(html: str) -> str:
    from html.parser import HTMLParser

    class _Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts: list[str] = []
            self._skip = 0
            self._skip_tags = {"script", "style", "head"}

        def handle_starttag(self, tag, attrs):
            if tag in self._skip_tags:
                self._skip += 1

        def handle_endtag(self, tag):
            if tag in self._skip_tags and self._skip > 0:
                self._skip -= 1

        def handle_data(self, data):
            if self._skip == 0:
                s = data.strip()
                if s:
                    self.parts.append(s)

    p = _Parser()
    p.feed(html)
    return " ".join(p.parts)


async def process_inbound_email(
    sender: str,
    subject: str,
    body: str,
    message_id: str,
    user_id: Optional[str] = None,
) -> Optional[RawContentItem]:
    """
    Process a pre-parsed inbound email (from webhook) and store it in Redis
    for the dispatcher to pick up on the next ingestion cycle.
    """
    try:
        uid = user_id or "unknown"
        msg_key = message_id.strip("<>") if message_id else str(uuid.uuid4())
        cache_key = f"newsletter:{uid}:{msg_key}"
        await cache_set(cache_key, {
            "subject": subject,
            "sender": sender,
            "body": body,
            "message_id": msg_key,
        }, ttl_seconds=48 * 3600)

        return RawContentItem(
            url=f"newsletter://{uid}/{msg_key}",
            title=subject or "Newsletter",
            author=sender or None,
            full_text=body or None,
            word_count=len(body.split()) if body else None,
        )
    except Exception as e:
        logger.error(f"Failed to process inbound email: {e}")
        return None


async def process_raw_email(raw_email: str, user_id: uuid.UUID) -> Optional[RawContentItem]:
    """Parse a raw RFC 2822 email string and store it. Legacy path."""
    try:
        msg = email_lib.message_from_string(raw_email)
        subject = msg.get("Subject", "Newsletter")
        sender = msg.get("From", "")
        message_id = msg.get("Message-ID", str(uuid.uuid4()))

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = _html_to_text(payload.decode("utf-8", errors="replace"))
                        break
                elif ctype == "text/plain" and not body:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="replace")

        return await process_inbound_email(
            sender=sender,
            subject=subject,
            body=body,
            message_id=message_id,
            user_id=str(user_id),
        )
    except Exception as e:
        logger.error(f"Failed to process raw email for user {user_id}: {e}")
        return None
