"""Queue latency and digest on-time summaries (#239), read from the samples
app.workers.queue_metrics writes."""

from __future__ import annotations

import time

import numpy as np

from app.config import get_settings
from app.workers.queue_metrics import hour_key


def _stats(samples: list[float]) -> dict:
    if not samples:
        return {"count": 0, "p50": None, "p95": None, "max": None}
    arr = np.asarray(samples, dtype=float)
    return {
        "count": int(arr.size),
        "p50": round(float(np.percentile(arr, 50)), 3),
        "p95": round(float(np.percentile(arr, 95)), 3),
        "max": round(float(arr.max()), 3),
    }


def queue_report(client, *, hours: int = 24, now: float | None = None) -> dict:
    """Seconds waited per queue, runtime per task, and digest on-time rate."""
    now = now or time.time()
    wanted = {hour_key(now - 3600 * h) for h in range(max(1, hours))}
    grouped: dict[tuple[str, str], list[float]] = {}
    for raw in client.scan_iter(match="qm:*", count=500):
        key = raw.decode() if isinstance(raw, bytes) else str(raw)
        try:
            _, kind, rest = key.split(":", 2)
            name, hour = rest.rsplit(":", 1)
        except ValueError:
            continue
        if hour not in wanted:
            continue
        values = [float(v) for v in client.lrange(key, 0, -1)]
        grouped.setdefault((kind, name), []).extend(values)

    slo = get_settings().digest_on_time_seconds
    e2e = grouped.get(("e2e", "digest"), [])
    on_time = sum(1 for v in e2e if v <= slo)
    return {
        "window_hours": hours,
        "queue_wait_seconds": {n: _stats(v) for (k, n), v in sorted(grouped.items()) if k == "lag"},
        "task_runtime_seconds": {
            n: _stats(v) for (k, n), v in sorted(grouped.items()) if k == "run"
        },
        "digest_delivery": {
            "slo_seconds": slo,
            "lateness_seconds": _stats(e2e),
            "on_time_ratio": round(on_time / len(e2e), 4) if e2e else None,
        },
    }
