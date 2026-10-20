#!/usr/bin/env python
"""Replay your own reading logs offline and compare rankers (#200).

1. Download your data: Preferences -> Export my data (account export,
   format 2 or later).
2. Run, on your own machine:

       cd backend && PYTHONPATH=. python scripts/replay_eval.py ~/weirling-export.json \\
           --out ../docs/eval/replay-$(date +%F).md --label "owner, 30 days"

Nothing is sent anywhere. Only the aggregate report is written; review it
before committing (it contains no titles, URLs or ids).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("export", type=Path, help="account export JSON")
    ap.add_argument("--out", type=Path, help="write the markdown report here")
    ap.add_argument("--label", default="owner replay")
    ap.add_argument("--test-days", type=int, default=7)
    args = ap.parse_args()

    from app.services.ranking.replay import evaluate, report_markdown
    from app.utils.embeddings import get_embedding_service

    export = json.loads(args.export.read_text())
    version = export.get("export_metadata", {}).get("format_version", 1)
    if version < 2:
        sys.exit("This export predates format 2 (no digest items); export your data again.")
    embedder = get_embedding_service()
    result = evaluate(export, embedder.encode, test_days=args.test_days)
    report = report_markdown(result, label=args.label)
    report += f"\nEmbedder: {embedder.model_name}\n"
    print(report)
    print(json.dumps(result, indent=2))
    if args.out:
        args.out.write_text(report)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
