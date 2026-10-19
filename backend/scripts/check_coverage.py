#!/usr/bin/env python
"""Fail when coverage drops below its floors (#189).

    python -m pytest --cov --cov-report=json:coverage.json
    python scripts/check_coverage.py coverage.json

The global floor is enforced by pytest-cov (--cov-fail-under); this adds
per-module floors for the hot paths, so a drop in the ranker or ingest can't
hide inside a healthy total. Floors sit a few points under the measured
value (2026-10-20); raise them when coverage improves, never lower them to
make a PR pass.
"""

from __future__ import annotations

import json
import sys

FLOORS: dict[str, float] = {
    "app/services/ranking/ranker.py": 95,
    "app/services/ranking/learner.py": 93,
    "app/services/digest/builder.py": 88,
    "app/services/feed_identity.py": 94,
    "app/services/ingestion/feeds.py": 90,
    "app/workers/tasks/ingest_feeds.py": 82,
    "app/workers/tasks/compute_embeddings.py": 70,
    "app/workers/tasks/update_interest_graph.py": 70,
    "app/services/interest_graph/updater.py": 92,
    "app/api/feedback.py": 78,
    "app/api/auth.py": 90,
    "app/services/billing/__init__.py": 95,
    "app/services/abuse.py": 95,
    "app/services/email_verification.py": 88,
}


def failures(report: dict, floors: dict[str, float] = FLOORS) -> list[str]:
    out = []
    files = report.get("files", {})
    for path, floor in floors.items():
        if path not in files:
            out.append(f"{path}: not measured (renamed or deleted? update FLOORS)")
            continue
        pct = files[path]["summary"]["percent_covered"]
        if pct < floor:
            out.append(f"{path}: {pct:.1f}% < floor {floor}%")
    return out


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else "coverage.json"
    with open(path) as fh:
        report = json.load(fh)
    problems = failures(report)
    total = report["totals"]["percent_covered"]
    print(f"coverage total {total:.1f}%; {len(FLOORS)} per-module floors checked")
    for line in problems:
        print(f"::error::coverage {line}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
