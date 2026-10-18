"""Per-user weight learning from within-digest preferences (#154).

Replaces the MSE step in meta_weights (which froze reading_depth and
explicit_feedback at their priors forever and counted unseen items as
failures). Each settled digest yields pairs "item the user preferred" vs
"item shown in the same digest they liked less", labeled by the phase2
label contract:

- unviewed skips never train (the user may not have seen the item);
- ratings, saves, re-reads and completion map to (label, confidence);
- exploration items are reweighted by clipped inverse propensity.

The features are the ones logged on the impression when the digest was
built, so the model learns from what it actually showed. One pairwise
logistic step per pair, L2 toward the default prior, simplex projection;
below MIN_PAIRS the weights stay at the prior. Every digest is trained on
exactly once (`trained_until`), and each update writes a revision row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import UserContentInteraction
from app.models.digest import Digest, DigestImpression, RankerWeightRevision
from app.models.meta_weights import UserMetaWeights as WeightsRow
from app.services.ranking.meta_weights import DEFAULT_WEIGHTS, cache_key
from app.services.ranking.phase2.contract import SIGNALS, label_event
from app.services.ranking.phase2.learning import (
    RANKER_VERSION,
    WeightState,
    clipped_ipw,
    project_simplex,
    update_weights,
)

# A digest is ready to train on once the user has had this long to read it.
SETTLE_AFTER = timedelta(hours=12)
MIN_LABEL_GAP = 0.25
MAX_PAIRS_PER_DIGEST = 60
MAX_DIGESTS_PER_RUN = 30
BASE_LR = 0.05


def prior_vector() -> np.ndarray:
    return project_simplex(np.array([DEFAULT_WEIGHTS[name] for name in SIGNALS], dtype=float))


def _features(row: DigestImpression) -> np.ndarray:
    raw = row.features_json or {}
    return np.array([float(raw.get(name, 0.5)) for name in SIGNALS], dtype=float)


def _label(ix: UserContentInteraction | None, *, viewed: bool, now: datetime):
    if ix is None:
        return None
    saved_unopened_days = None
    if ix.saved and ix.opened_at is None and ix.saved_at is not None:
        saved_at = ix.saved_at if ix.saved_at.tzinfo else ix.saved_at.replace(tzinfo=UTC)
        saved_unopened_days = (now - saved_at).total_seconds() / 86400
    skipped = bool(ix.skipped) or (
        ix.opened_at is None and not ix.saved and ix.explicit_rating is None
    )
    return label_event(
        completion=ix.read_completion_pct if ix.opened_at is not None else None,
        rating=ix.explicit_rating,
        saved=bool(ix.saved),
        skipped=skipped,
        reread=int(ix.re_read_count or 0),
        viewed=viewed,
        reason=ix.explicit_rating_reason,
        saved_unopened_days=saved_unopened_days,
    )


def digest_pairs(
    impressions: list[DigestImpression],
    interactions: dict[uuid.UUID, UserContentInteraction],
    *,
    now: datetime,
) -> list[tuple[np.ndarray, np.ndarray, float]]:
    """(preferred features, other features, step weight) pairs for one digest."""
    viewed = any(i.viewed for i in impressions) or any(
        (ix := interactions.get(i.content_item_id)) is not None and ix.opened_at is not None
        for i in impressions
    )
    labeled = []
    for imp in impressions:
        result = _label(interactions.get(imp.content_item_id), viewed=viewed, now=now)
        if result is None:
            continue
        label, confidence = result
        ipw = clipped_ipw(imp.propensity) if imp.exploration else 1.0
        labeled.append((label, confidence, ipw, _features(imp)))
    labeled.sort(key=lambda row: row[0], reverse=True)
    pairs: list[tuple[np.ndarray, np.ndarray, float]] = []
    for i, (li, ci, wi, fi) in enumerate(labeled):
        for lj, cj, wj, fj in labeled[i + 1 :]:
            if li - lj < MIN_LABEL_GAP:
                continue
            weight = min(ci, cj) * max(wi, wj)
            pairs.append((fi, fj, weight))
            if len(pairs) >= MAX_PAIRS_PER_DIGEST:
                return pairs
    return pairs


async def train_user(
    user_id: uuid.UUID, session: AsyncSession, *, now: datetime | None = None
) -> dict:
    """Learn from settled digests not yet trained on; persist and log a revision."""
    from app.utils.cache import cache_delete

    now = now or datetime.now(UTC)
    row = (
        await session.execute(select(WeightsRow).where(WeightsRow.user_id == user_id))
    ).scalar_one_or_none()
    prior = prior_vector()
    if row is None:
        row = WeightsRow(
            user_id=user_id,
            weights={name: float(prior[i]) for i, name in enumerate(SIGNALS)},
            update_count=0,
            pairs_seen=0,
        )
        session.add(row)
        await session.flush()

    query = (
        select(Digest)
        .where(Digest.user_id == user_id, Digest.generated_at <= now - SETTLE_AFTER)
        .order_by(Digest.generated_at.asc())
        .limit(MAX_DIGESTS_PER_RUN)
    )
    if row.trained_until is not None:
        query = query.where(Digest.generated_at > row.trained_until)
    digests = list((await session.execute(query)).scalars())
    if not digests:
        return {"status": "nothing_new", "pairs": 0}

    weights = np.array([float(row.weights.get(name, prior[i])) for i, name in enumerate(SIGNALS)])
    state = WeightState(project_simplex(weights), RANKER_VERSION, row.update_count, row.pairs_seen)
    pairs_used = 0
    for digest in digests:
        impressions = list(
            (
                await session.execute(
                    select(DigestImpression).where(
                        DigestImpression.digest_id == digest.id, DigestImpression.user_id == user_id
                    )
                )
            ).scalars()
        )
        ids = [imp.content_item_id for imp in impressions]
        interactions = (
            {
                ix.content_item_id: ix
                for ix in (
                    await session.execute(
                        select(UserContentInteraction).where(
                            UserContentInteraction.user_id == user_id,
                            UserContentInteraction.content_item_id.in_(ids),
                        )
                    )
                ).scalars()
            }
            if ids
            else {}
        )
        for preferred, other, weight in digest_pairs(impressions, interactions, now=now):
            state = update_weights(state, preferred, other, lr=BASE_LR * weight, prior=prior)
            pairs_used += 1

    trained_until = max(d.generated_at for d in digests)
    row.trained_until = trained_until
    row.pairs_seen = state.pairs_seen
    if pairs_used:
        row.weights = state.as_dict()
        row.update_count = state.updates
        session.add(
            RankerWeightRevision(user_id=user_id, version=RANKER_VERSION, weights=state.as_dict())
        )
    await session.flush()
    await cache_delete(cache_key(user_id))
    return {"status": "ok", "pairs": pairs_used, "digests": len(digests), "weights": row.weights}
