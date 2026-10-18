#!/usr/bin/env python
"""Offline ranking-eval report (audit 05-9).

Runs the held-out ranking-eval harness (services/ranking/evaluation.py) across
all users and prints a per-signup-week cohort summary of read-prediction AUC and
Spearman(PRS, completion) — the falsifiable "does the PRS predict reads, and is
it improving?" view the audit asks for. A runnable script rather than a Jupyter
notebook so it can live in the repo and run in CI/containers unchanged:

    python scripts/ranking_eval.py --days 30
    python scripts/ranking_eval.py --synthetic
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


async def _run(days: int) -> None:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.ranking.evaluation import evaluate_user_ranking

    async with AsyncSessionLocal() as session:
        users = list((await session.execute(select(User))).scalars())
        if not users:
            print("No users.")
            return

        cohorts: dict[str, list] = defaultdict(list)
        for user in users:
            result = await evaluate_user_ranking(user.id, session, days=days)
            if result.n == 0:
                continue
            week = user.created_at.strftime("%G-W%V")
            cohorts[week].append(result)

    if not cohorts:
        print(f"No scored engagement in the last {days} days.")
        return

    print(
        f"Ranking eval (Observed Engagement — Not Synthetic) — last {days} days, "
        f"{sum(len(v) for v in cohorts.values())} users\n"
    )
    print(
        f"{'cohort':<12} {'users':>6} {'PRS_AUC':>9} {'no_learn':>9} {'oracle':>7} {'mean_rho':>9} {'reads':>7}"
    )
    print("-" * 65)
    for week in sorted(cohorts):
        evals = cohorts[week]
        aucs = [e.read_prediction_auc for e in evals if e.read_prediction_auc is not None]
        no_learns = [e.no_learning_auc for e in evals if e.no_learning_auc is not None]
        oracles = [e.oracle_auc for e in evals if e.oracle_auc is not None]
        rhos = [e.spearman_completion for e in evals if e.spearman_completion is not None]
        auc = f"{mean(aucs):.3f}" if aucs else "  n/a"
        nl = f"{mean(no_learns):.3f}" if no_learns else "  n/a"
        orc = f"{mean(oracles):.3f}" if oracles else "  n/a"
        rho = f"{mean(rhos):.3f}" if rhos else "  n/a"
        reads = sum(e.positives for e in evals)
        print(f"{week:<12} {len(evals):>6} {auc:>9} {nl:>9} {orc:>7} {rho:>9} {reads:>7}")

    all_aucs = [
        e.read_prediction_auc
        for evals in cohorts.values()
        for e in evals
        if e.read_prediction_auc is not None
    ]
    all_nl = [
        e.no_learning_auc
        for evals in cohorts.values()
        for e in evals
        if e.no_learning_auc is not None
    ]
    if all_aucs:
        nl_str = f"{mean(all_nl):.3f}" if all_nl else "n/a"
        print(f"\nOverall mean read-prediction AUC (observed): {mean(all_aucs):.3f}")
        print("Baselines for read-prediction AUC:")
        print("  - Chance / Random baseline:   0.500 (uninformative order)")
        print(f"  - No-learning baseline:       {nl_str} (uniform weights on signals)")
        print("  - Oracle baseline:            1.000 (perfect separation)")
        print("  - Production target:          > 0.600 and rising")


def run_synthetic() -> None:
    from app.services.ranking.learning import synthetic_eval

    report = synthetic_eval()
    print("=" * 64)
    print("SYNTHETIC RANKING EVALUATION BENCHMARK (Unit Test for Learner)")
    print("CAVEAT: Synthetic simulation only — not real user engagement.")
    print("=" * 64)
    print("Baselines (NDCG@10 across synthetic personas):")
    print(f"  - PRS (learned weights):              {report.prs_ndcg:.4f}")
    print(f"  - Oracle (upper bound, ground truth): {report.oracle_ndcg:.4f}")
    print(f"  - No-learning (uniform prior weights): {report.no_learning_ndcg:.4f}")
    print(f"  - Semantic-only (first feature):       {report.semantic_ndcg:.4f}")
    print(f"  - Chronological (ingest order):        {report.chronological_ndcg:.4f}")
    print(f"  - Random (permutation):                {report.random_ndcg:.4f}")
    print("\nMargins & Gate:")
    print(f"  - Margin over chronological:          {report.margin:.4f}")
    print(f"  - Margin over no-learning:            {report.margin_over_no_learning:.4f}")
    print(f"  - Gate passed (beats all non-oracle by >= 0.05): {report.beats_baselines()}")
    print("=" * 64)


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline ranking-eval report")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Run synthetic ranking evaluation benchmark (unit test of learner mechanics; NOT real users)",
    )
    # Read-only by default (#199): without --write the report is only printed
    # and the tree stays clean.
    parser.add_argument(
        "--write",
        metavar="PATH",
        default=None,
        help="Also write the report text to PATH (e.g. docs/eval/ranking-observed.md)",
    )
    args = parser.parse_args()
    if args.synthetic:
        run_synthetic()
        return

    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        asyncio.run(_run(args.days))
    report = buffer.getvalue()
    sys.stdout.write(report)
    if args.write:
        Path(args.write).write_text(report, encoding="utf-8")
        print(f"Wrote report to {args.write}")


if __name__ == "__main__":
    main()
