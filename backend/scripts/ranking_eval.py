#!/usr/bin/env python
"""Offline ranking-eval report (audit 05-9).

Runs the held-out ranking-eval harness (services/ranking/evaluation.py) across
all users and prints a per-signup-week cohort summary of read-prediction AUC and
Spearman(PRS, completion) — the falsifiable "does the PRS predict reads, and is
it improving?" view the audit asks for. A runnable script rather than a Jupyter
notebook so it can live in the repo and run in CI/containers unchanged:

    docker compose exec backend python scripts/ranking_eval.py --days 30
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from statistics import mean


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

    print(f"Ranking eval — last {days} days, {sum(len(v) for v in cohorts.values())} users\n")
    print(f"{'cohort':<12} {'users':>6} {'mean_AUC':>9} {'mean_rho':>9} {'reads':>7}")
    print("-" * 48)
    for week in sorted(cohorts):
        evals = cohorts[week]
        aucs = [e.read_prediction_auc for e in evals if e.read_prediction_auc is not None]
        rhos = [e.spearman_completion for e in evals if e.spearman_completion is not None]
        auc = f"{mean(aucs):.3f}" if aucs else "  n/a"
        rho = f"{mean(rhos):.3f}" if rhos else "  n/a"
        reads = sum(e.positives for e in evals)
        print(f"{week:<12} {len(evals):>6} {auc:>9} {rho:>9} {reads:>7}")

    all_aucs = [
        e.read_prediction_auc
        for evals in cohorts.values()
        for e in evals
        if e.read_prediction_auc is not None
    ]
    if all_aucs:
        print(
            f"\nOverall mean read-prediction AUC: {mean(all_aucs):.3f} "
            f"(0.5 = chance; target > 0.6 and rising)"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline ranking-eval report")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    args = parser.parse_args()
    asyncio.run(_run(args.days))


if __name__ == "__main__":
    main()
