"""First fetch keeps the newest N items. Later digests cap items per source."""

from __future__ import annotations

from datetime import datetime


def newest_n(items: list, limit: int) -> list:
    if limit <= 0 or len(items) <= limit:
        return list(items)

    def stamp(item) -> datetime:
        published = getattr(item, "published_at", None)
        return published or datetime.min

    ordered = sorted(items, key=stamp, reverse=True)
    return ordered[:limit]


def cap_per_source(items: list, cap: int) -> list:
    """Keep digest order, but no source contributes more than ``cap`` items."""
    if cap <= 0:
        return list(items)
    counts: dict[object, int] = {}
    kept = []
    for item in items:
        key = getattr(item, "source_id", None)
        used = counts.get(key, 0)
        if key is not None and used >= cap:
            continue
        counts[key] = used + 1
        kept.append(item)
    return kept
