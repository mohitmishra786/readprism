from __future__ import annotations

import hashlib
import json
import logging
import sys

from app.config import get_settings


def sanitize_log(value: object) -> str:
    """Strip CR/LF (and other control chars) from a value before it's logged.

    Prevents log-injection / forged log lines when user-controlled data (URLs,
    ids, cache keys) is interpolated into a log message (CodeQL py/log-injection).
    """
    text = str(value)
    return "".join(ch if ch == "\t" or ch >= " " else " " for ch in text).replace("\n", " ")


def mask_email(value: object) -> str:
    """One-way hash of an email for logs (#198): correlation without PII.

    Log lines must not carry email addresses; a short digest still lets an
    operator match repeated sends to the same recipient.
    """
    return "email:" + hashlib.sha256(str(value).encode()).hexdigest()[:12]


class _SanitizingFormatter(logging.Formatter):
    """Formatter that neutralizes newlines/control chars in the final message, so
    no log record can inject additional lines regardless of the call site."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return "".join(ch if ch in "\n\t" or ch >= " " else " " for ch in formatted)


class _JSONFormatter(logging.Formatter):
    """One JSON object per log line (#198).

    The message is passed through `sanitize_log` (same log-injection rule as
    the text formatter), so structured output still cannot be forged with
    embedded newlines. Extra record attributes are surfaced as JSON keys.
    """

    RESERVED = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
        "asctime",
        "message",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_log(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and not key.startswith("_"):
                payload[key] = sanitize_log(value) if isinstance(value, str) else value
        if record.exc_info and record.exc_info[1] is not None:
            payload["error"] = sanitize_log(str(record.exc_info[1]))
        return json.dumps(payload, default=str)


def setup_logging(level: str | None = None, fmt: str | None = None) -> None:
    settings = get_settings()
    chosen_fmt = (fmt or settings.log_format).lower()
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(stream=sys.stdout)
    if chosen_fmt == "json":
        handler.setFormatter(_JSONFormatter())
    else:
        handler.setFormatter(
            _SanitizingFormatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    root.addHandler(handler)
    root.setLevel(getattr(logging, (level or "INFO").upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
