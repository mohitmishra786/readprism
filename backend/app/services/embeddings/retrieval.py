"""Golden retrieval. Two hundred fixture pairs, no downloaded model weights.

The truncated encoder only sees the opening of each document. The full encoder
sees the topic token wherever it sits. Nomic is not loaded here; the ADR
records that the default stays MiniLM until that model is compared on this
same harness.
"""

from __future__ import annotations

from app.services.embeddings.registry import MINILM_DIM, hash_embed


def corpus(size: int = 200) -> list[dict[str, str]]:
    rows = []
    for index in range(size):
        topic = f"topic{index % 20}"
        other = f"topic{(index + 7) % 20}"
        rows.append(
            {
                "query": f"find {topic} essays",
                "relevant": "intro words " * 12 + f"late section discusses {topic} in detail",
                "irrelevant": "intro words " * 12 + f"late section discusses {other} in detail",
            }
        )
    return rows


def _truncated(text: str) -> list[float]:
    return hash_embed(" ".join(text.split()[:8]), MINILM_DIM)


def _full(text: str) -> list[float]:
    return hash_embed(text, MINILM_DIM)


def _mrr(encoder) -> float:
    reciprocal = 0.0
    rows = corpus()
    for row in rows:
        query = encoder(row["query"])
        relevant = _cosine(query, encoder(row["relevant"]))
        irrelevant = _cosine(query, encoder(row["irrelevant"]))
        if relevant > irrelevant + 1e-9:
            reciprocal += 1.0
        elif abs(relevant - irrelevant) <= 1e-9:
            reciprocal += 0.5
    return reciprocal / len(rows)


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = sum(value * value for value in left) ** 0.5 or 1.0
    right_norm = sum(value * value for value in right) ** 0.5 or 1.0
    return dot / (left_norm * right_norm)


def compare() -> dict[str, float | int | bool]:
    full = _mrr(_full)
    truncated = _mrr(_truncated)
    return {
        "pairs": 200,
        "full_mrr": full,
        "truncated_mrr": truncated,
        "full_wins": full > truncated,
    }


def backfill_batch(
    rows: list[dict], *, model: str, dim: int, version: str, cursor: int, size: int
) -> dict:
    """Resumable metadata stamp. The vector column is left untouched."""
    chosen = rows[cursor : cursor + size]
    for row in chosen:
        row["embedding_model"] = model
        row["embedding_dim"] = dim
        row["embedding_version"] = version
    nxt = cursor + len(chosen)
    return {"stamped": len(chosen), "next_cursor": nxt, "done": nxt >= len(rows)}
