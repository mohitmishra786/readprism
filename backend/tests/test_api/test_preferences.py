"""Preferences API: digest length lock semantics (UX-02)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _auth_header(client: AsyncClient, data: dict) -> dict:
    resp = await client.post("/api/v1/auth/register", json=data)
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_setting_length_explicitly_locks_it(client: AsyncClient, test_user_data: dict):
    headers = await _auth_header(client, test_user_data)

    resp = await client.put("/api/v1/preferences", json={"digest_max_items": 9}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["digest_max_items"] == 9
    assert body["digest_length_locked"] is True


@pytest.mark.asyncio
async def test_auto_flag_unlocks_length(client: AsyncClient, test_user_data: dict):
    headers = await _auth_header(client, test_user_data)

    resp = await client.put("/api/v1/preferences", json={"digest_max_items": 9}, headers=headers)
    assert resp.json()["digest_length_locked"] is True

    resp = await client.put(
        "/api/v1/preferences", json={"digest_length_auto": True}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["digest_length_locked"] is False
    # The explicit value stays until the learner moves it.
    assert resp.json()["digest_max_items"] == 9


@pytest.mark.asyncio
async def test_default_is_unlocked(client: AsyncClient, test_user_data: dict):
    headers = await _auth_header(client, test_user_data)
    resp = await client.get("/api/v1/preferences", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["digest_length_locked"] is False
    assert resp.json()["send_time_locked"] is False


@pytest.mark.asyncio
async def test_setting_time_explicitly_locks_it(client: AsyncClient, test_user_data: dict):
    headers = await _auth_header(client, test_user_data)

    resp = await client.put(
        "/api/v1/preferences", json={"digest_time_morning": "08:30:00"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["send_time_locked"] is True

    # The learned-histogram job never moves an explicit time after that.
    resp = await client.put("/api/v1/preferences", json={"send_time_auto": True}, headers=headers)
    assert resp.json()["send_time_locked"] is False


@pytest.mark.asyncio
async def test_onboarding_time_choice_persists_and_locks_the_send_time(client, test_user_data):
    """#201: the final onboarding step's payload pins the time; the learner skips it."""
    from unittest.mock import patch

    from app.models.user import User
    from tests.conftest import TestingSessionLocal

    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    resp = await client.put(
        "/api/v1/preferences",
        json={
            "digest_frequency": "daily",
            "digest_time_morning": "06:30:00",
            "timezone": "Asia/Kolkata",
        },
        headers=headers,
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["digest_time_morning"] == "06:30:00" and body["timezone"] == "Asia/Kolkata"
    assert body["send_time_locked"] is True

    from sqlalchemy import select

    from app.workers.tasks.build_digest import _learn_send_times_async

    async with TestingSessionLocal() as s:
        user = (
            await s.execute(select(User).where(User.email == test_user_data["email"]))
        ).scalar_one()
        user.onboarding_complete = True
        await s.commit()
    with patch("app.database.AsyncSessionLocal", TestingSessionLocal):
        await _learn_send_times_async()
    again = (await client.get("/api/v1/preferences", headers=headers)).json()
    assert again["digest_time_morning"] == "06:30:00"


@pytest.mark.asyncio
async def test_interest_graph_serves_the_map(client, test_user_data, db_session):
    """#179: up to 300 nodes on request, with recency and mute state."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.models.interest_graph import InterestNode
    from app.models.user import User

    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    now = datetime.now(UTC)
    for i in range(120):
        db_session.add(
            InterestNode(
                user_id=user.id,
                topic_label=f"topic {i}",
                weight=1 - i / 200,
                last_reinforced_at=now - timedelta(days=i),
                reinforcement_count=i,
                suppressed_until=now + timedelta(days=7) if i == 5 else None,
            )
        )
    await db_session.commit()

    default = (await client.get("/api/v1/preferences/interest-graph", headers=headers)).json()
    assert len(default["nodes"]) == 50
    big = (await client.get("/api/v1/preferences/interest-graph?limit=300", headers=headers)).json()
    assert len(big["nodes"]) == 120
    muted = next(n for n in big["nodes"] if n["label"] == "topic 5")
    assert (
        muted["suppressed_until"]
        and muted["reinforcement_count"] == 5
        and muted["last_reinforced_at"]
    )
    too_many = await client.get("/api/v1/preferences/interest-graph?limit=1000", headers=headers)
    assert too_many.status_code == 422
