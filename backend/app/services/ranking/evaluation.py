"""Ranking-eval harness: is the PRS actually predicting what users read?

The whole "it learns" claim rests on predicted PRS ranking items the user then
engages with. This module measures that on *held-out* observed engagement, so
the claim is falsifiable rather than "trust me, it converges" (audit 05-1 /
16-3 / 17-4).

Two dependency-free metrics (no sklearn/scipy):
- **Read-prediction AUC**: ROC-AUC of predicted PRS vs the binary "did the user
  open this item", computed exactly via the Mann-Whitney U statistic. 0.5 = no
  better than chance; > 0.6 and rising is the target.
- **Spearman rank correlation** between predicted PRS and read completion.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import UserContentInteraction
from app.models.digest import Digest, DigestItem


@dataclass
class RankingEval:
    n: int  # number of scored items with observed engagement
    read_prediction_auc: float | None  # None when one class is absent
    spearman_completion: float | None  # None when <2 points or no variance
    positives: int  # items that were opened


def read_prediction_auc(scores: list[float], labels: list[bool]) -> float | None:
    """Exact ROC-AUC via the Mann-Whitney U statistic (handles ties)."""
    pos = [s for s, y in zip(scores, labels, strict=True) if y]
    neg = [s for s, y in zip(scores, labels, strict=True) if not y]
    if not pos or not neg:
        return None
    # Rank all scores (average ranks for ties), sum ranks of positives.
    ranks = _average_ranks(scores)
    pos_rank_sum = sum(r for r, y in zip(ranks, labels, strict=True) if y)
    n_pos, n_neg = len(pos), len(neg)
    u = pos_rank_sum - n_pos * (n_pos + 1) / 2
    return u / (n_pos * n_neg)


def spearman(x: list[float], y: list[float]) -> float | None:
    """Spearman rank correlation (Pearson on ranks). None if <2 pts or no variance."""
    if len(x) < 2:
        return None
    rx, ry = _average_ranks(x), _average_ranks(y)
    return _pearson(rx, ry)


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1  # 1-based average rank for the tie group
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((ai - ma) * (bi - mb) for ai, bi in zip(a, b, strict=True))
    va = sum((ai - ma) ** 2 for ai in a)
    vb = sum((bi - mb) ** 2 for bi in b)
    if va == 0 or vb == 0:
        return None
    return cov / (va**0.5 * vb**0.5)


async def evaluate_user_ranking(
    user_id: uuid.UUID, session: AsyncSession, *, days: int = 30
) -> RankingEval:
    """Evaluate how well the PRS predicted this user's reads over the last `days`.

    Joins digest items (which carry the predicted prs_score at delivery time) to
    the user's interaction record (opened / completion), so we compare the
    prediction to the *subsequently observed* behaviour.
    """
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        await session.execute(
            select(DigestItem.prs_score, UserContentInteraction)
            .join(Digest, DigestItem.digest_id == Digest.id)
            .join(
                UserContentInteraction,
                (UserContentInteraction.content_item_id == DigestItem.content_item_id)
                & (UserContentInteraction.user_id == Digest.user_id),
            )
            .where(Digest.user_id == user_id, Digest.generated_at >= since)
        )
    ).all()

    scores: list[float] = []
    opened: list[bool] = []
    completion_scores: list[float] = []
    completions: list[float] = []
    for prs_score, interaction in rows:
        if prs_score is None:
            continue
        scores.append(float(prs_score))
        was_opened = interaction.opened_at is not None
        opened.append(was_opened)
        if interaction.read_completion_pct is not None:
            completion_scores.append(float(prs_score))
            completions.append(float(interaction.read_completion_pct))

    return RankingEval(
        n=len(scores),
        read_prediction_auc=read_prediction_auc(scores, opened),
        spearman_completion=spearman(completion_scores, completions),
        positives=sum(opened),
    )
