"""Embedding input: title, lead, and up to four body windows, encoded separately.

MiniLM keeps about 256 tokens. Each piece stays short enough to encode on its
own. The title vector is weighted twice when the pieces are pooled.
"""

from __future__ import annotations

WINDOW = 180
MAX_WINDOWS = 4


def windows(body: str) -> list[str]:
    words = (body or "").split()
    chunks = [" ".join(words[start : start + WINDOW]) for start in range(0, len(words), WINDOW)]
    return [chunk for chunk in chunks[:MAX_WINDOWS] if chunk]


def embedding_pieces(*, title: str, lead: str = "", body: str = "") -> list[str]:
    parts: list[str] = []
    if title.strip():
        parts.append(title.strip())
    if lead.strip():
        parts.append(lead.strip())
    parts.extend(windows(body))
    return parts


def pool_vectors(vectors: list[list[float]], *, title_weight: float = 2.0) -> list[float]:
    if not vectors:
        return []
    width = len(vectors[0])
    total = [0.0] * width
    for index, vector in enumerate(vectors):
        weight = title_weight if index == 0 else 1.0
        for slot, value in enumerate(vector):
            total[slot] += weight * float(value)
    norm = sum(value * value for value in total) ** 0.5 or 1.0
    return [value / norm for value in total]


def build_embedding_input(*, title: str, lead: str = "", body: str = "") -> str:
    pieces = embedding_pieces(title=title, lead=lead, body=body)
    if pieces:
        pieces = [pieces[0], pieces[0], *pieces[1:]]
    return "\n".join(pieces)


def prefix_only(*, title: str, body: str, words: int = 40) -> str:
    return f"{title} " + " ".join(body.split()[:words])
