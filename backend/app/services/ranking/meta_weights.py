from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.cache import cache_get, cache_set
from app.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_WEIGHTS = {
    "semantic": 0.25,
    "reading_depth": 0.15,
    "suggestion": 0.20,
    "explicit_feedback": 0.15,
    "source_trust": 0.10,
    "content_quality": 0.05,
    "temporal_context": 0.07,
    "novelty": 0.03,
}
MIN_INTERACTIONS_FOR_LEARNING = 20
CACHE_TTL = 24 * 3600


class UserMetaWeights:
    def __init__(
        self,
        user_id: uuid.UUID,
        weights: dict[str, float] | None = None,
        last_updated: datetime | None = None,
        update_count: int = 0,
    ) -> None:
        self.user_id = user_id
        self.weights = weights or dict(DEFAULT_WEIGHTS)
        self.last_updated = last_updated or datetime.now(timezone.utc)
        self.update_count = update_count
        self._normalize()

    def _normalize(self) -> None:
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: v / total for k, v in self.weights.items()}

    def to_dict(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "weights": self.weights,
            "last_updated": self.last_updated.isoformat(),
            "update_count": self.update_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserMetaWeights":
        return cls(
            user_id=uuid.UUID(data["user_id"]),
            weights=data["weights"],
            last_updated=datetime.fromisoformat(data["last_updated"]),
            update_count=data.get("update_count", 0),
        )


async def get_meta_weights(user_id: uuid.UUID, session: AsyncSession) -> UserMetaWeights:
    cache_key = f"meta_weights:{user_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return UserMetaWeights.from_dict(cached)

    # Fall back to DB
    from sqlalchemy import select
    from app.models.meta_weights import UserMetaWeights as UserMetaWeightsModel
    result = await session.execute(
        select(UserMetaWeightsModel).where(UserMetaWeightsModel.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        obj = UserMetaWeights(
            user_id=user_id,
            weights=row.weights,
            update_count=row.update_count,
        )
        await cache_set(cache_key, obj.to_dict(), ttl_seconds=CACHE_TTL)
        return obj

    return UserMetaWeights(user_id=user_id)


async def update_meta_weights(
    user_id: uuid.UUID,
    digest_items_with_interactions: list[tuple],
    session: AsyncSession,
) -> UserMetaWeights:
    """
    Gradient descent update of meta weights.
    digest_items_with_interactions: list of (DigestItem, UserContentInteraction)
    """
    if len(digest_items_with_interactions) < MIN_INTERACTIONS_FOR_LEARNING:
        return await get_meta_weights(user_id, session)

    weights_obj = await get_meta_weights(user_id, session)
    weights = weights_obj.weights

    step_size = 0.01
    gradients: dict[str, float] = {k: 0.0 for k in weights}
    n = 0

    for digest_item, interaction in digest_items_with_interactions:
        if interaction is None or interaction.read_completion_pct is None:
            continue

        # Actual engagement
        rating_norm = 0.0
        if interaction.explicit_rating is not None:
            rating_norm = float(interaction.explicit_rating)  # -1, 0, or 1
        actual = (
            (interaction.read_completion_pct or 0.0) * 0.5
            + rating_norm * 0.3
            + (1.0 if interaction.saved else 0.0) * 0.2
        )
        actual = max(0.0, min(1.0, actual))

        # Predicted PRS from signal breakdown
        breakdown = digest_item.signal_breakdown or {}
        predicted = sum(weights.get(k, 0.0) * v for k, v in breakdown.items())
        error = predicted - actual

        for signal_name, signal_score in breakdown.items():
            if signal_name in gradients:
                gradients[signal_name] += 2 * error * signal_score
        n += 1

    if n == 0:
        return weights_obj

    for k in weights:
        weights[k] = weights[k] - step_size * (gradients[k] / n)
        weights[k] = max(0.01, min(0.50, weights[k]))

    weights_obj.weights = weights
    weights_obj._normalize()
    weights_obj.update_count += 1
    weights_obj.last_updated = datetime.now(timezone.utc)

    cache_key = f"meta_weights:{user_id}"
    await cache_set(cache_key, weights_obj.to_dict(), ttl_seconds=CACHE_TTL)

    # Persist to DB (upsert)
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.meta_weights import UserMetaWeights as UserMetaWeightsModel
    result = await session.execute(
        select(UserMetaWeightsModel).where(UserMetaWeightsModel.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        row.weights = weights_obj.weights
        row.update_count = weights_obj.update_count
    else:
        row = UserMetaWeightsModel(
            user_id=user_id,
            weights=weights_obj.weights,
            update_count=weights_obj.update_count,
        )
        session.add(row)
    await session.flush()

    return weights_obj
