"""Evaluate synthetic ranking harness and optionally write docs/eval/ranking.md."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.ranking.phase2.learning import EvalReport, synthetic_eval


def render_report(report: EvalReport) -> str:
    return "\n".join(
        [
            "# Ranking Eval (Synthetic Benchmark)",
            "",
            "> [!NOTE]",
            "> **Synthetic Sanity Check Only:**",
            "> This benchmark measures learner mechanics and gradient convergence on synthetically",
            "> generated users and i.i.d. random feature vectors with single-feature dominance.",
            "> It does **not** evaluate real-world human reading satisfaction or real-world item ranking quality.",
            "> Production engagement is evaluated on observed user interactions via `scripts/ranking_eval.py`.",
            "",
            "## Method",
            "Synthetic users, one dominant signal each. Weights are learned with",
            "pairwise updates on a training split. PRS is the held-out score",
            "from those weights, not a sort of the labels. Chronological keeps",
            "ingest order. Semantic-only uses the first feature. Random is a",
            "permutation. No-learning uses fixed uniform prior weights without updates.",
            "Oracle sorts directly by true held-out relevance (upper bound).",
            "NDCG@10 is the mean across users.",
            "",
            "## Baselines",
            f"- PRS NDCG@10 (learned): {report.prs_ndcg:.4f}",
            f"- Oracle NDCG@10 (upper bound): {report.oracle_ndcg:.4f}",
            f"- No-learning NDCG@10 (default prior weights): {report.no_learning_ndcg:.4f}",
            f"- Semantic-only NDCG@10: {report.semantic_ndcg:.4f}",
            f"- Chronological NDCG@10: {report.chronological_ndcg:.4f}",
            f"- Random NDCG@10: {report.random_ndcg:.4f}",
            "",
            "## Margins & Gate",
            f"- Margin over chronological: {report.margin:.4f}",
            f"- Margin over no-learning: {report.margin_over_no_learning:.4f}",
            "",
            "Gate: PRS beats each non-oracle baseline (chronological, semantic-only, random, no-learning) by at least 0.05.",
            f"Passed: {report.beats_baselines()}",
            "",
            "## Retrieval & Latency Fixtures",
            "Retrieval fixture (200 pairs, no Nomic weights): see `make retrieval-eval`.",
            "A tie between the two candidates scores expected reciprocal rank 0.75.",
            "Default embedding stays all-MiniLM-L6-v2 because the stored column is 384-d.",
            "See ADR 0004.",
            "",
            "Linear score of a 1000 by 8 feature matrix is covered by",
            "`test_exploration_ipw_and_eval_gate`. A full digest build against",
            "1,000 database rows was not timed. Celery sets `task_acks_late`.",
            "Task de-dup keys are `task_dedup_key`.",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synthetic ranking evaluation benchmark (unit test for learner mechanics)"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write evaluation output to docs/eval/ranking.md (default: read-only, print to stdout)",
    )
    args = parser.parse_args()

    report = synthetic_eval()
    output = render_report(report)
    print(output)

    if args.write:
        backend = Path(__file__).resolve().parents[1]
        root = backend.parent if (backend.parent / "docs").is_dir() else backend
        target = root / "docs" / "eval" / "ranking.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
        print(f"Updated {target}")

    if not report.beats_baselines():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
