"""Turn a forwarded newsletter into stored content.

Prefer the HTML part, drop tracking pixels, unwrap redirect links without
requesting them, and surface confirmation and unsubscribe links. Re-sends
share a message-id key.
"""

from __future__ import annotations

import email as email_lib
import hashlib
import hmac
from dataclasses import dataclass, field
from email.message import Message
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from app.utils.sanitize import sanitize_stored_html
from app.utils.ssrf import UnsafeURLError, validate_public_url

_UNWRAP_KEYS = ("url", "u", "redirect")
_PIXEL_HINTS = ("pixel", "track", "open", "beacon")


@dataclass
class ParsedNewsletter:
    sender: str
    recipient: str
    subject: str
    message_id: str
    text: str
    html: str
    list_unsubscribe: str | None = None
    view_in_browser: str | None = None
    is_confirmation: bool = False
    dedupe_key: str = ""
    headers: dict[str, str] = field(default_factory=dict)


def verify_body_hmac(*, secret: str, payload: bytes, signature: str) -> bool:
    if not secret or not signature or payload is None:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    presented = signature.strip()
    if presented.lower().startswith("sha256="):
        presented = presented.split("=", 1)[1]
    return hmac.compare_digest(expected, presented)


def parse_imap_batch(messages: list[bytes]) -> list[ParsedNewsletter]:
    """Parse RFC822 messages an IMAP poller already fetched. No socket is opened."""
    return [parse_rfc822(raw) for raw in messages]


def parse_rfc822(raw: str | bytes) -> ParsedNewsletter:
    if isinstance(raw, bytes):
        message = email_lib.message_from_bytes(raw)
    else:
        message = email_lib.message_from_string(raw)
    return _from_message(message)


def parse_html_body(
    *,
    sender: str,
    recipient: str,
    subject: str,
    message_id: str,
    html: str | None = None,
    text: str | None = None,
    list_unsubscribe: str | None = None,
) -> ParsedNewsletter:
    cleaned_html, view = _clean_html(html or "")
    plain = (text or _html_to_text(cleaned_html)).strip()
    confirmation = _is_confirmation(subject, plain)
    key = (message_id or "").strip().strip("<>") or hashlib.sha256(
        f"{sender}|{subject}|{plain[:200]}".encode()
    ).hexdigest()
    return ParsedNewsletter(
        sender=sender.strip(),
        recipient=recipient.strip(),
        subject=subject.strip() or "Newsletter",
        message_id=key,
        text=plain,
        html=cleaned_html,
        list_unsubscribe=list_unsubscribe,
        view_in_browser=view,
        is_confirmation=confirmation,
        dedupe_key=key,
    )


def recipient_token(address: str) -> str | None:
    """``u.{token}@domain`` or the local part after ``+``."""
    local = address.split("@", 1)[0].lower()
    if local.startswith("u.") and len(local) > 2:
        return local[2:]
    if "+" in local:
        token = local.split("+", 1)[1]
        return token or None
    return None


def _from_message(message: Message) -> ParsedNewsletter:
    html = ""
    text = ""
    if message.is_multipart():
        for part in message.walk():
            kind = part.get_content_type()
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes):
                continue
            decoded = payload.decode("utf-8", errors="replace")
            if kind == "text/html" and not html:
                html = decoded
            elif kind == "text/plain" and not text:
                text = decoded
    else:
        payload = message.get_payload(decode=True)
        decoded = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else ""
        if message.get_content_type() == "text/html":
            html = decoded
        else:
            text = decoded
    return parse_html_body(
        sender=str(message.get("From") or ""),
        recipient=str(message.get("To") or ""),
        subject=str(message.get("Subject") or "Newsletter"),
        message_id=str(message.get("Message-ID") or message.get("Message-Id") or ""),
        html=html,
        text=text,
        list_unsubscribe=message.get("List-Unsubscribe"),
    )


def _clean_html(html: str) -> tuple[str, str | None]:
    if not html:
        return "", None
    soup = BeautifulSoup(html, "html.parser")
    view = None
    for image in list(soup.find_all("img")):
        if _is_pixel(image):
            image.decompose()
    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not href:
            continue
        label = anchor.get_text(" ", strip=True).lower()
        unwrapped = unwrap_link(str(href))
        anchor["href"] = unwrapped
        if view is None and ("view in browser" in label or "read online" in label):
            view = unwrapped
    return sanitize_stored_html(str(soup)), view


def unwrap_link(href: str) -> str:
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    for key in _UNWRAP_KEYS:
        values = query.get(key) or []
        if not values:
            continue
        target = values[0]
        if not target.startswith(("http://", "https://")):
            continue
        try:
            validate_public_url(target)
        except UnsafeURLError:
            continue
        return target
    return href


def _is_pixel(image) -> bool:
    src = str(image.get("src") or "").lower()
    if any(hint in src for hint in _PIXEL_HINTS):
        return True
    for attr in ("width", "height"):
        raw = str(image.get(attr) or "").strip()
        if raw.isdigit() and int(raw) <= 1:
            return True
    return False


def _is_confirmation(subject: str, body: str) -> bool:
    blob = f"{subject} {body}".lower()
    return "confirm" in blob and ("subscription" in blob or "subscribe" in blob)


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def parse_postmark(payload: dict) -> ParsedNewsletter:
    headers = {
        str(item.get("Name", "")): str(item.get("Value", ""))
        for item in payload.get("Headers") or []
        if isinstance(item, dict)
    }
    return parse_html_body(
        sender=str(payload.get("From") or ""),
        recipient=str(payload.get("To") or ""),
        subject=str(payload.get("Subject") or "Newsletter"),
        message_id=str(payload.get("MessageID") or ""),
        html=payload.get("HtmlBody") or "",
        text=payload.get("TextBody") or "",
        list_unsubscribe=headers.get("List-Unsubscribe"),
    )


def parse_resend(payload: dict) -> ParsedNewsletter:
    nested = payload.get("data")
    data = nested if isinstance(nested, dict) else payload
    recipient = data.get("to") or ""
    if isinstance(recipient, list):
        recipient = recipient[0] if recipient else ""
    return parse_html_body(
        sender=str(data.get("from") or ""),
        recipient=str(recipient),
        subject=str(data.get("subject") or "Newsletter"),
        message_id=str(data.get("email_id") or data.get("message_id") or ""),
        html=data.get("html") or "",
        text=data.get("text") or "",
    )


def parse_cloudflare(payload: dict) -> ParsedNewsletter:
    raw_headers = payload.get("headers")
    headers = raw_headers if isinstance(raw_headers, dict) else {}
    return parse_html_body(
        sender=str(payload.get("from") or ""),
        recipient=str(payload.get("to") or ""),
        subject=str(payload.get("subject") or "Newsletter"),
        message_id=str(payload.get("message_id") or payload.get("messageId") or ""),
        html=payload.get("html") or payload.get("raw") or "",
        text=payload.get("text") or "",
        list_unsubscribe=headers.get("list-unsubscribe") or headers.get("List-Unsubscribe"),
    )
