"""UX-06: every reason tag maps to its documented label and side effects."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.interest_graph import InterestNode
from app.models.source import Source
from app.models.user import User
from app.services.ranking.feedback_map import REASON_EFFECTS, reason_effect


def test_mapping_table_matches_the_spec_labels():
    # A4: too basic / already knew -> 0.35 / 0.8
    assert REASON_EFFECTS["too_basic"].label_y == 0.35
    assert REASON_EFFECTS["too_basic"].confidence == 0.8
    assert REASON_EFFECTS["already_knew"].label_y == 0.35
    # A4: off-topic -> 0.0 / 1.0 (and the legacy spelling behaves the same)
    assert REASON_EFFECTS["off_topic"].label_y == 0.0
    assert REASON_EFFECTS["off_topic"].confidence == 1.0
    assert REASON_EFFECTS["too_tangential"].label_y == REASON_EFFECTS["off_topic"].label_y
    # wrong_depth is calibration-only: no cluster or source effect
    assert REASON_EFFECTS["wrong_depth"].cluster_weight_delta == 0.0
    assert REASON_EFFECTS["wrong_depth"].source_trust_delta == 0.0
    # clickbait hits the source, not the cluster
    assert REASON_EFFECTS["clickbait"].source_trust_delta < 0
    assert REASON_EFFECTS["clickbait"].cluster_weight_delta == 0.0


def test_reason_effect_returns_none_for_unknown():
    assert reason_effect(None) is None
    assert reason_effect("mystery") is None


def test_label_event_uses_the_mapping():
    from app.services.ranking.phase2.contract import label_event

    y, c = label_event(rating=-1, reason="off_topic")
    assert (y, c) == (0.0, 1.0)
    y, c = label_event(rating=-1, reason="too_basic")
    assert (y, c) == (0.35, 0.8)
    # Unmapped reason falls back to the plain-rating rules.
    assert label_event(rating=-1, reason="mystery") == (0.0, 1.0)


async def _seed(client: AsyncClient, db_session, data: dict):
    resp = await client.post("/api/v1/auth/register", json=data)
    assert resp.status_code == 201
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (await db_session.execute(select(User).where(User.email == data["email"]))).scalar_one()
    source = Source(user_id=user.id, url="https://fb.example/feed", trust_weight=0.6)
    db_session.add(source)
    await db_session.flush()
    content = ContentItem(
        source_id=source.id,
        url="https://fb.example/a",
        title="Tagged",
        topic_clusters=["ai"],
        fetched_at=datetime.now(UTC),
    )
    db_session.add(content)
    db_session.add(InterestNode(user_id=user.id, topic_label="ai", weight=0.8))
    await db_session.commit()
    return user, source, content, headers


async def _post_reason(client: AsyncClient, content, reason: str, headers: dict):
    with patch(
        "app.workers.tasks.update_interest_graph.update_interest_graph_for_interaction.delay"
    ):
        resp = await client.post(
            "/api/v1/feedback/interaction",
            json={
                "content_item_id": str(content.id),
                "explicit_rating": -1,
                "explicit_rating_reason": reason,
            },
            headers=headers,
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_off_topic_weakens_the_cluster(client: AsyncClient, test_user_data: dict, db_session):
    user, _source, content, headers = await _seed(client, db_session, test_user_data)
    await _post_reason(client, content, "off_topic", headers)

    node = (
        await db_session.execute(
            select(InterestNode).where(
                InterestNode.user_id == user.id, InterestNode.topic_label == "ai"
            )
        )
    ).scalar_one()
    assert node.weight == pytest.approx(0.8 - 0.20)


@pytest.mark.asyncio
async def test_clickbait_lowers_source_trust_not_cluster(
    client: AsyncClient, test_user_data: dict, db_session
):
    user, source, content, headers = await _seed(client, db_session, test_user_data)
    await _post_reason(client, content, "clickbait", headers)

    await db_session.refresh(source)
    assert source.trust_weight == pytest.approx(0.6 - 0.10)
    node = (
        await db_session.execute(
            select(InterestNode).where(
                InterestNode.user_id == user.id, InterestNode.topic_label == "ai"
            )
        )
    ).scalar_one()
    assert node.weight == pytest.approx(0.8)  # untouched


@pytest.mark.asyncio
async def test_wrong_depth_changes_nothing_but_the_label(
    client: AsyncClient, test_user_data: dict, db_session
):
    user, source, content, headers = await _seed(client, db_session, test_user_data)
    await _post_reason(client, content, "wrong_depth", headers)

    await db_session.refresh(source)
    node = (
        await db_session.execute(
            select(InterestNode).where(
                InterestNode.user_id == user.id, InterestNode.topic_label == "ai"
            )
        )
    ).scalar_one()
    assert node.weight == pytest.approx(0.8)
    assert source.trust_weight == pytest.approx(0.6)
    interaction = (
        await db_session.execute(
            select(UserContentInteraction).where(
                UserContentInteraction.user_id == user.id,
                UserContentInteraction.content_item_id == content.id,
            )
        )
    ).scalar_one()
    assert interaction.explicit_rating == -1
    assert interaction.explicit_rating_reason == "wrong_depth"


@pytest.mark.asyncio
async def test_reason_effects_apply_once_per_stored_reason(
    client: AsyncClient, test_user_data: dict, db_session
):
    """A retried POST with the same reason must not compound the delta."""
    user, _source, content, headers = await _seed(client, db_session, test_user_data)
    await _post_reason(client, content, "off_topic", headers)
    await _post_reason(client, content, "off_topic", headers)  # retry

    node = (
        await db_session.execute(
            select(InterestNode).where(
                InterestNode.user_id == user.id, InterestNode.topic_label == "ai"
            )
        )
    ).scalar_one()
    assert node.weight == pytest.approx(0.8 - 0.20)  # applied once

    # A changed reason applies its own effect once.
    await _post_reason(client, content, "too_basic", headers)
    await db_session.refresh(node)
    assert node.weight == pytest.approx(0.8 - 0.20 - 0.10)


@pytest.mark.asyncio
async def test_cluster_delta_hits_only_the_top_cluster(
    client: AsyncClient, test_user_data: dict, db_session
):
    """topic_clusters[0] is the top cluster; other labels stay untouched."""
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    source = Source(user_id=user.id, url="https://fb.example/f2", trust_weight=0.6)
    db_session.add(source)
    await db_session.flush()
    content = ContentItem(
        source_id=source.id,
        url="https://fb.example/top",
        title="Top",
        topic_clusters=["ai", "ml"],
        fetched_at=datetime.now(UTC),
    )
    db_session.add(content)
    db_session.add(InterestNode(user_id=user.id, topic_label="ai", weight=0.8))
    db_session.add(InterestNode(user_id=user.id, topic_label="ml", weight=0.7))
    await db_session.commit()

    await _post_reason(client, content, "off_topic", headers)

    ai = (
        await db_session.execute(
            select(InterestNode).where(
                InterestNode.user_id == user.id, InterestNode.topic_label == "ai"
            )
        )
    ).scalar_one()
    ml = (
        await db_session.execute(
            select(InterestNode).where(
                InterestNode.user_id == user.id, InterestNode.topic_label == "ml"
            )
        )
    ).scalar_one()
    assert ai.weight == pytest.approx(0.6)
    assert ml.weight == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_delivery_skips_already_delivered_digest(db_session):
    """A delivery retry must not send a second email."""
    from unittest.mock import patch as mock_patch

    from app.models.digest import Digest
    from app.services.digest.delivery import deliver_digest

    user = User(email="delivered@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    digest = Digest(
        user_id=user.id,
        generated_at=datetime.now(UTC),
        delivered_at=datetime.now(UTC),
        delivery_method="in_app",
        section_counts={},
        total_items=5,
    )
    db_session.add(digest)
    await db_session.commit()

    with mock_patch("app.services.digest.delivery.send_email") as mock_send:
        ok = await deliver_digest(digest, user, db_session)
    assert ok is True
    mock_send.assert_not_called()
