"""Embedding input: title twice, the lead, and up to four body windows.

A topic that appears only past the first window still enters the pooled text,
which is the difference from a truncated prefix.
"""

from __future__ import annotations

WINDOW = 400
MAX_WINDOWS = 4


def windows(body: str) -> list[str]:
    words = (body or "").split()
    chunks = [" ".join(words[start : start + WINDOW]) for start in range(0, len(words), WINDOW)]
    return [chunk for chunk in chunks[:MAX_WINDOWS] if chunk]


def build_embedding_input(*, title: str, lead: str = "", body: str = "") -> str:
    parts = [title.strip(), title.strip()]
    if lead.strip():
        parts.append(lead.strip())
    parts.extend(windows(body))
    return "\n".join(part for part in parts if part)


def prefix_only(*, title: str, body: str, words: int = 40) -> str:
    return f"{title} " + " ".join(body.split()[:words])
