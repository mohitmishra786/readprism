"""Saved-queue intent semantics (UX-12)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.services.ranking.phase2.contract import label_event


def test_saved_then_fully_read_is_a_strong_positive():
    assert label_event(saved=True, completion=0.95) == (1.0, 1.2)
    # Not fully read: stays the moderate save signal.
    assert label_event(saved=True, completion=0.4) == (0.9, 0.8)
    assert label_event(saved=True) == (0.9, 0.8)


def test_saved_unopened_14_days_is_a_slight_negative():
    assert label_event(saved=True, saved_unopened_days=14) == (0.4, 0.3)
    assert label_event(saved=True, saved_unopened_days=30) == (0.4, 0.3)
    # Before the deadline the plain save signal holds.
    assert label_event(saved=True, saved_unopened_days=6) == (0.9, 0.8)


def test_derive_saved_unopened_days():
    now = datetime(2026, 10, 2, tzinfo=UTC)
    saved_at = now - timedelta(days=20)
    opened = None
    days = (now - saved_at).days if not opened else None
    assert label_event(saved=True, saved_unopened_days=days) == (0.4, 0.3)


@pytest.mark.asyncio
async def test_save_sets_saved_at(client: AsyncClient, test_user_data: dict, db_session):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    content = ContentItem(
        url="https://saved.example/a", title="To read", fetched_at=datetime.now(UTC)
    )
    db_session.add(content)
    await db_session.commit()

    from unittest.mock import patch

    with patch(
        "app.workers.tasks.update_interest_graph.update_interest_graph_for_interaction.delay"
    ):
        resp = await client.post(
            "/api/v1/feedback/interaction",
            json={"content_item_id": str(content.id), "saved": True},
            headers=headers,
        )
    assert resp.status_code == 200

    interaction = (
        await db_session.execute(
            select(UserContentInteraction).where(
                UserContentInteraction.user_id == user.id,
                UserContentInteraction.content_item_id == content.id,
            )
        )
    ).scalar_one()
    assert interaction.saved_at is not None


@pytest.mark.asyncio
async def test_saved_queue_lists_unread_saves_first(
    client: AsyncClient, test_user_data: dict, db_session
):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    now = datetime.now(UTC)

    unread = ContentItem(url="https://q.example/unread", title="Unread", fetched_at=now)
    done = ContentItem(url="https://q.example/done", title="Done", fetched_at=now)
    db_session.add_all([unread, done])
    await db_session.flush()
    db_session.add(
        UserContentInteraction(user_id=user.id, content_item_id=unread.id, saved=True, saved_at=now)
    )
    db_session.add(
        UserContentInteraction(
            user_id=user.id,
            content_item_id=done.id,
            saved=True,
            saved_at=now - timedelta(days=1),
            saved_read_at=now,  # already read: leaves the queue
        )
    )
    await db_session.commit()

    result = await client.get("/api/v1/content/saved", headers=headers)
    assert result.status_code == 200
    titles = [row["content"]["title"] for row in result.json()]
    assert titles == ["Unread"]
