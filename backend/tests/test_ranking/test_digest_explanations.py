"""Every digest item carries a faithful explanation (#99).

Items with a precomputed `prs_score` used to reach the builder with the
breakdown `{"_cached": True}`, so they got no `contributions`, no
explanation, and empty impression features.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import DigestImpression, DigestItem
from app.models.source import Source
from app.models.user import User
from app.services.digest.builder import build_digest
from app.services.ranking.phase2.contract import SIGNALS
from app.services.ranking.phase2.learning import faithful


async def _seed_with_cached_scores(db_session, n: int = 8) -> User:
    user = User(email="explained@example.com", hashed_password="x", onboarding_complete=True)
    db_session.add(user)
    await db_session.flush()
    src = Source(user_id=user.id, url="https://explained.example/feed", name="E")
    db_session.add(src)
    await db_session.flush()
    for i in range(n):
        item = ContentItem(
            source_id=src.id,
            url=f"https://explained.example/{i}",
            title=f"Item {i}",
            fetched_at=datetime.now(UTC),
            rankable=True,
            word_count=600 + i * 100,
            reading_time_minutes=3 + i,
            topic_clusters=[f"t{i % 3}"],
        )
        db_session.add(item)
        await db_session.flush()
        # Stale score from an earlier precompute run.
        db_session.add(
            UserContentInteraction(user_id=user.id, content_item_id=item.id, prs_score=0.9)
        )
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_cached_items_still_get_faithful_contributions(db_session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "digest_per_source_cap", 20)
    user = await _seed_with_cached_scores(db_session)

    digest = await build_digest(user, db_session)
    await db_session.commit()

    items = list(
        (
            await db_session.execute(select(DigestItem).where(DigestItem.digest_id == digest.id))
        ).scalars()
    )
    assert items, "digest should not be empty"
    for di in items:
        breakdown = di.signal_breakdown
        assert "_cached" not in breakdown
        assert breakdown.get("explanation"), breakdown
        contributions = breakdown["contributions"]
        assert set(contributions) <= set(SIGNALS)
        assert faithful(contributions, di.prs_score)
        # The stale cached value must not survive: scores are recomputed.
        assert di.prs_score != pytest.approx(0.9)

    impressions = list(
        (
            await db_session.execute(
                select(DigestImpression).where(DigestImpression.digest_id == digest.id)
            )
        ).scalars()
    )
    assert impressions and all(imp.features_json for imp in impressions)
