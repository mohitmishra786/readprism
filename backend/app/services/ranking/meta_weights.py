from __future__ import annotations

import uuid
from datetime import UTC, datetime

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
CACHE_TTL = 24 * 3600


def cache_key(user_id: uuid.UUID) -> str:
    return f"meta_weights:{user_id}"


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
        self.last_updated = last_updated or datetime.now(UTC)
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
    def from_dict(cls, data: dict) -> UserMetaWeights:
        return cls(
            user_id=uuid.UUID(data["user_id"]),
            weights=data["weights"],
            last_updated=datetime.fromisoformat(data["last_updated"]),
            update_count=data.get("update_count", 0),
        )


async def get_meta_weights(user_id: uuid.UUID, session: AsyncSession) -> UserMetaWeights:
    cached = await cache_get(cache_key(user_id))
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
        await cache_set(cache_key(user_id), obj.to_dict(), ttl_seconds=CACHE_TTL)
        return obj

    return UserMetaWeights(user_id=user_id)
