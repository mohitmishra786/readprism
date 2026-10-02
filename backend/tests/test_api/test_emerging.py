"""Emerging-topics detector (UX-10): burst detected, steady state not."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.source import Source
from app.models.user import User
from app.services.digest.emerging import detect_emerging


def test_synthetic_burst_is_detected():
    # Topic "ai": baseline ~1 source/week; last 72h has 5 sources.
    recent = {"ai": 5}
    history = {"ai": [1.0, 1.0, 1.0, 1.0]}
    found = detect_emerging(recent, history)
    assert [e.topic for e in found] == ["ai"]
    assert found[0].recent_sources == 5
    assert found[0].z >= 2


def test_steady_state_is_not_detected():
    recent = {"ai": 1}
    history = {"ai": [1.0, 1.0, 1.0, 1.0]}
    assert detect_emerging(recent, history) == []


def test_flat_baseline_burst_is_an_outlier():
    """Zero variance does not hide a burst (std == 0 branch)."""
    found = detect_emerging({"rust": 3}, {"rust": [0.0, 0.0, 0.0, 0.0]})
    assert [e.topic for e in found] == ["rust"]
    assert found[0].z == float("inf")


def test_needs_two_baseline_windows_and_min_sources():
    # Single baseline window: not enough history.
    assert detect_emerging({"ai": 5}, {"ai": [1.0]}) == []
    # One source in 72h: below min_sources even with flat baseline.
    assert detect_emerging({"ai": 1}, {"ai": [0.0, 0.0, 0.0, 0.0]}) == []


@pytest.mark.asyncio
async def test_emerging_endpoint_finds_a_burst(
    client: AsyncClient, test_user_data: dict, db_session
):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()

    now = datetime.now(UTC)
    # 5 distinct sources covering "ai" in the last 72h.
    for i in range(5):
        src = Source(user_id=user.id, url=f"https://burst-{i}.example/feed")
        db_session.add(src)
        await db_session.flush()
        db_session.add(
            ContentItem(
                source_id=src.id,
                url=f"https://burst-{i}.example/{i}",
                title=f"burst-{i}",
                topic_clusters=["ai"],
                fetched_at=now - timedelta(hours=i + 1),
            )
        )
    # Baseline weeks: quiet (one source in week 1 only, for "ai").
    quiet = Source(user_id=user.id, url="https://quiet.example/feed")
    db_session.add(quiet)
    await db_session.flush()
    db_session.add(
        ContentItem(
            source_id=quiet.id,
            url="https://quiet.example/a",
            title="quiet",
            topic_clusters=["ai"],
            fetched_at=now - timedelta(days=25),
        )
    )
    await db_session.commit()

    result = await client.get("/api/v1/digest/emerging", headers=headers)
    assert result.status_code == 200
    topics = [row["topic"] for row in result.json()]
    assert "ai" in topics
