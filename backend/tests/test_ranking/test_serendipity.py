"""Interest-adjacent serendipity candidate selection (audit 04-1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.content import ContentItem
from app.models.interest_graph import InterestNode
from app.models.user import User
from app.services.digest.builder import _select_serendipity_candidates


def _vec(*first_values: float) -> list[float]:
    v = [0.0] * 384
    for i, val in enumerate(first_values):
        v[i] = val
    return v


@pytest.mark.asyncio
async def test_serendipity_prefers_adjacent_over_core_and_unrelated(db_session):
    user = User(email="s@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    # Interest vector points along e1.
    db_session.add(
        InterestNode(user_id=user.id, topic_label="t", weight=1.0, topic_embedding=_vec(1.0))
    )

    now = datetime.now(UTC)
    core = ContentItem(  # cosine 1.0 -> distance 0 -> too close (core)
        url="https://x/core", title="core", embedding=_vec(1.0), fetched_at=now
    )
    adjacent = ContentItem(  # cosine 0.6 -> distance 0.4 -> in the adjacency band
        url="https://x/adj", title="adj", embedding=_vec(0.6, 0.8), fetched_at=now
    )
    unrelated = ContentItem(  # cosine 0.0 -> distance 1.0 -> unrelated
        url="https://x/unrel", title="unrel", embedding=_vec(0.0, 1.0), fetched_at=now
    )
    db_session.add_all([core, adjacent, unrelated])
    await db_session.commit()

    cutoff = now - timedelta(hours=24)
    picked = await _select_serendipity_candidates(user, [], cutoff, 5, db_session)
    titles = {c.title for c in picked}

    assert "adj" in titles
    assert "core" not in titles  # too close to established interest
    assert "unrel" not in titles  # too far to be relevant


@pytest.mark.asyncio
async def test_serendipity_falls_back_to_recent_without_interest_vector(db_session):
    """A brand-new user (no interest nodes) still gets recent public content."""
    user = User(email="new@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(UTC)
    db_session.add(
        ContentItem(url="https://x/recent", title="recent", fetched_at=now, embedding=_vec(0.5))
    )
    await db_session.commit()

    picked = await _select_serendipity_candidates(
        user, [], now - timedelta(hours=24), 5, db_session
    )
    assert any(c.title == "recent" for c in picked)
