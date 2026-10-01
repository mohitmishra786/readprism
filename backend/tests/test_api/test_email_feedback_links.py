"""Signed one-click email feedback links (UX-04).

Covers: signature round-trip, tamper and expiry rejection, and the
unauthenticated endpoints that record feedback and redirect to the reader.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.utils.signed_links import action_url, verify_action


def test_signed_link_round_trip():
    uid, item = uuid.uuid4(), uuid.uuid4()
    url = action_url(uid, item, "up")
    assert "/api/v1/digest/e/up/" in url
    # Extract params back out of the URL and verify.
    query = url.split("?", 1)[1]
    params = dict(part.split("=", 1) for part in query.split("&"))
    assert verify_action(params["uid"], item, "up", int(params["exp"]), params["sig"]) is True


def test_tampered_signature_is_rejected():
    uid, item = uuid.uuid4(), uuid.uuid4()
    url = action_url(uid, item, "down")
    query = url.split("?", 1)[1]
    params = dict(part.split("=", 1) for part in query.split("&"))
    bad = "0" * 64 if params["sig"] != "0" * 64 else "1" * 64
    assert verify_action(params["uid"], item, "down", int(params["exp"]), bad) is False


def test_expired_link_is_rejected():
    uid, item = uuid.uuid4(), uuid.uuid4()
    exp = int(time.time()) - 10
    url = action_url(uid, item, "save", ttl_seconds=-10)
    query = url.split("?", 1)[1]
    params = dict(part.split("=", 1) for part in query.split("&"))
    assert int(params["exp"]) == exp
    assert verify_action(params["uid"], item, "save", exp, params["sig"]) is False


def test_action_cannot_be_replayed_as_another_action():
    uid, item = uuid.uuid4(), uuid.uuid4()
    url = action_url(uid, item, "up")
    query = url.split("?", 1)[1]
    params = dict(part.split("=", 1) for part in query.split("&"))
    # A valid 'up' signature must not authorize 'down'.
    assert verify_action(params["uid"], item, "down", int(params["exp"]), params["sig"]) is False


async def _seed(client: AsyncClient, db_session, data: dict):
    resp = await client.post("/api/v1/auth/register", json=data)
    assert resp.status_code == 201
    user = (await db_session.execute(select(User).where(User.email == data["email"]))).scalar_one()
    content = ContentItem(
        url="https://email-fb.example/a", title="Signed", fetched_at=datetime.now(UTC)
    )
    db_session.add(content)
    await db_session.commit()
    return user, content


@pytest.mark.asyncio
async def test_up_link_records_rating_and_redirects(
    client: AsyncClient, test_user_data: dict, db_session
):
    user, content = await _seed(client, db_session, test_user_data)
    url = action_url(user.id, content.id, "up")

    with patch(
        "app.workers.tasks.update_interest_graph.update_interest_graph_for_interaction.delay"
    ) as mock_delay:
        resp = await client.get(url)
    assert resp.status_code == 303
    assert f"/read/{content.id}" in resp.headers["location"]
    mock_delay.assert_called_once()

    interaction = (
        await db_session.execute(
            select(UserContentInteraction).where(
                UserContentInteraction.user_id == user.id,
                UserContentInteraction.content_item_id == content.id,
            )
        )
    ).scalar_one()
    assert interaction.explicit_rating == 1
    assert interaction.opened_at is not None


@pytest.mark.asyncio
async def test_save_link_records_saved(client: AsyncClient, test_user_data: dict, db_session):
    user, content = await _seed(client, db_session, test_user_data)
    url = action_url(user.id, content.id, "save")

    with patch(
        "app.workers.tasks.update_interest_graph.update_interest_graph_for_interaction.delay"
    ):
        resp = await client.get(url)
    assert resp.status_code == 303

    await db_session.refresh(
        (
            await db_session.execute(
                select(UserContentInteraction).where(
                    UserContentInteraction.user_id == user.id,
                    UserContentInteraction.content_item_id == content.id,
                )
            )
        ).scalar_one()
    )
    interaction = (
        await db_session.execute(
            select(UserContentInteraction).where(
                UserContentInteraction.user_id == user.id,
                UserContentInteraction.content_item_id == content.id,
            )
        )
    ).scalar_one()
    assert interaction.saved is True


@pytest.mark.asyncio
async def test_open_link_marks_opened_without_rating(
    client: AsyncClient, test_user_data: dict, db_session
):
    user, content = await _seed(client, db_session, test_user_data)
    url = action_url(user.id, content.id, "open")

    resp = await client.get(url)
    assert resp.status_code == 303

    interaction = (
        await db_session.execute(
            select(UserContentInteraction).where(
                UserContentInteraction.user_id == user.id,
                UserContentInteraction.content_item_id == content.id,
            )
        )
    ).scalar_one()
    assert interaction.opened_at is not None
    assert interaction.explicit_rating is None


@pytest.mark.asyncio
async def test_bad_signature_is_rejected(client: AsyncClient, test_user_data: dict, db_session):
    user, content = await _seed(client, db_session, test_user_data)
    url = action_url(user.id, content.id, "up")
    tampered = (
        url.replace("sig=", "sig=deadbeef")
        if "sig=deadbeef" not in url
        else url.replace("sig=deadbeef", "sig=other")
    )

    resp = await client.get(tampered)
    assert resp.status_code == 401

    rows = (
        await db_session.execute(
            select(UserContentInteraction).where(
                UserContentInteraction.user_id == user.id,
                UserContentInteraction.content_item_id == content.id,
            )
        )
    ).scalar_one_or_none()
    assert rows is None  # nothing recorded
