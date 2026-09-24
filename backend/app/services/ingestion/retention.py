"""Retention plan: age cutoff, per-source cap, and a storage summary.

The scheduled job applies the plan. ``ANALYZE`` is left to that job so tests
can assert the plan without a database.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta


def retention_plan(
    rows: list[dict],
    *,
    now: datetime,
    retention_days: int,
    per_source_cap: int,
    excerpt_chars: int,
) -> dict:
    """``rows`` need id, source_id, fetched_at, and text_length."""
    prune_ids: list = []
    if retention_days > 0:
        cutoff = now - timedelta(days=retention_days)
        for row in rows:
            if row["fetched_at"] < cutoff and row.get("text_length", 0) > excerpt_chars:
                prune_ids.append(row["id"])

    by_source: dict[object, list] = defaultdict(list)
    for row in rows:
        by_source[row["source_id"]].append(row)
    cap_ids: list = []
    if per_source_cap > 0:
        for grouped in by_source.values():
            ordered = sorted(grouped, key=lambda row: row["fetched_at"], reverse=True)
            cap_ids.extend(row["id"] for row in ordered[per_source_cap:])

    return {
        "prune_full_text": prune_ids,
        "over_cap": cap_ids,
        "analyze": True,
    }


def storage_stats(rows: list[dict]) -> dict:
    by_source: dict[str, int] = defaultdict(int)
    chars = 0
    for row in rows:
        length = int(row.get("text_length") or 0)
        chars += length
        by_source[str(row.get("source_id"))] += length
    return {
        "items": len(rows),
        "full_text_chars": chars,
        "by_source": dict(by_source),
    }
