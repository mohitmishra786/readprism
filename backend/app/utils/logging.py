from __future__ import annotations

import logging
import sys


def sanitize_log(value: object) -> str:
    """Strip CR/LF (and other control chars) from a value before it's logged.

    Prevents log-injection / forged log lines when user-controlled data (URLs,
    ids, cache keys) is interpolated into a log message (CodeQL py/log-injection).
    """
    text = str(value)
    return "".join(ch if ch == "\t" or ch >= " " else " " for ch in text).replace("\n", " ")


class _SanitizingFormatter(logging.Formatter):
    """Formatter that neutralizes newlines/control chars in the final message, so
    no log record can inject additional lines regardless of the call site."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return "".join(ch if ch in "\n\t" or ch >= " " else " " for ch in formatted)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        _SanitizingFormatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
