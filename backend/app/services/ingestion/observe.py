"""Ingestion metrics computed from sources and items already in hand."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from app.utils.logging import get_logger, sanitize_log

logger = get_logger(__name__)


def log_ingest(source_id: object, event: str, **fields: object) -> None:
    parts = [f"source_id={sanitize_log(source_id)}", f"event={sanitize_log(event)}"]
    for key, value in fields.items():
        parts.append(f"{sanitize_log(key)}={sanitize_log(value)}")
    logger.info("ingest %s", " ".join(parts))


def ingestion_report(sources: list, items: list, *, now: datetime | None = None) -> dict:
    del now
    active = [source for source in sources if getattr(source, "is_active", True)]
    healthy = [
        source
        for source in active
        if getattr(source, "feed_status", "healthy") in {"healthy", "degraded"}
    ]
    fetch_rate = (len(healthy) / len(active)) if active else 1.0
    methods: Counter[str] = Counter()
    failed = 0
    lags: list[float] = []
    for item in items:
        method = getattr(item, "extraction_method", None) or "unknown"
        methods[method] += 1
        if method == "failed":
            failed += 1
        fetched = getattr(item, "fetched_at", None)
        scored = getattr(item, "scored_at", None)
        if fetched is not None and scored is not None:
            lags.append((scored - fetched).total_seconds())
    extracted = sum(methods.values())
    success = ((extracted - failed) / extracted) if extracted else 1.0
    return {
        "sources": len(active),
        "fetch_success_rate": round(fetch_rate, 4),
        "extraction_success_rate": round(success, 4),
        "extraction_by_method": dict(methods),
        "ingest_to_scored_p50_seconds": _percentile(lags, 0.5),
        "ingest_to_scored_samples": len(lags),
    }


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)
