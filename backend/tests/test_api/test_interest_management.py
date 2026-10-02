"""Interest management endpoints (UX-08) + language filter (UX-15)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.interest_graph import InterestNode
from app.models.source import Source
from app.models.user import User


@pytest.mark.asyncio
async def test_rename_interest(client: AsyncClient, test_user_data: dict, db_session):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    db_session.add(InterestNode(user_id=user.id, topic_label="ml", weight=0.6))
    await db_session.commit()

    result = await client.post(
        "/api/v1/feedback/rename-interest",
        json={"from_label": "ml", "to_label": "machine learning"},
        headers=headers,
    )
    assert result.status_code == 200
    labels = {
        n.topic_label
        for n in (
            await db_session.execute(
                select(InterestNode).where(InterestNode.user_id == user.id)
            )
        ).scalars()
    }
    assert labels == {"machine learning"}


@pytest.mark.asyncio
async def test_merge_interests_sums_weights(client: AsyncClient, test_user_data: dict, db_session):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    db_session.add(InterestNode(user_id=user.id, topic_label="llm", weight=0.4))
    db_session.add(InterestNode(user_id=user.id, topic_label="ml", weight=0.5))
    await db_session.commit()

    result = await client.post(
        "/api/v1/feedback/merge-interests",
        json={"from_label": "llm", "into_label": "ml"},
        headers=headers,
    )
    assert result.status_code == 200
    nodes = {
        n.topic_label: n.weight
        for n in (
            await db_session.execute(
                select(InterestNode).where(InterestNode.user_id == user.id)
            )
        ).scalars()
    }
    assert nodes == {"ml": pytest.approx(0.9)}


@pytest.mark.asyncio
async def test_language_preference_round_trip_and_filter(
    client: AsyncClient, test_user_data: dict, db_session
):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()

    result = await client.put(
        "/api/v1/preferences",
        json={"preferred_languages": ["EN", "de", "x"]},
        headers=headers,
    )
    assert result.status_code == 200
    # "x" is dropped, codes lowercased.
    assert result.json()["preferred_languages"] == ["en", "de"]

    src = Source(user_id=user.id, url="https://lang.example/feed")
    db_session.add(src)
    await db_session.flush()
    en_item = ContentItem(
        source_id=src.id, url="https://lang.example/en", title="English",
        language="en", fetched_at=datetime.now(UTC), word_count=500,
    )
    fr_item = ContentItem(
        source_id=src.id, url="https://lang.example/fr", title="Français",
        language="fr", fetched_at=datetime.now(UTC), word_count=500,
    )
    unknown = ContentItem(
        source_id=src.id, url="https://lang.example/unk", title="Unknown",
        language=None, fetched_at=datetime.now(UTC), word_count=500,
    )
    db_session.add_all([en_item, fr_item, unknown])
    await db_session.commit()

    from app.services.digest.builder import build_digest

    with (
        patch("app.services.summarization.groq_client.GroqSummarizer", side_effect=Exception("no llm")),
        patch("app.workers.tasks.update_interest_graph.update_interest_graph_for_interaction.delay"),
        patch("app.workers.tasks.compute_embeddings.compute_embedding_for_item.delay"),
        patch("app.services.digest.builder.rank_content_for_user") as mock_rank,
    ):
        mock_rank.return_value = [(en_item, 0.8, {}), (unknown, 0.7, {})]
        digest = await build_digest(user, db_session)
    # The French item was filtered out before ranking; unknown stays.
    item_ids = {str(di.content_item_id) for di in digest.__dict__.get("_items", [])}
    # build_digest returns the Digest, items were added to the session — query them.
    from app.models.digest import DigestItem as DI

    rows = (
        await db_session.execute(select(DI).where(DI.digest_id == digest.id))
    ).scalars().all()
    placed = {str(r.content_item_id) for r in rows}
    assert str(en_item.id) in placed
    assert str(unknown.id) in placed
    assert str(fr_item.id) not in placed
