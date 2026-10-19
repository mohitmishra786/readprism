"""Calibration ratings in the wizard change the day-0 ranking (#149)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.interest_graph import InterestNode
from app.models.source import Source
from app.models.user import User
from app.services.ranking.ranker import rank
from app.utils.embeddings import get_embedding_service


async def _item(db_session, src, topic: str) -> ContentItem:
    vector = await get_embedding_service().encode_single(topic)
    item = ContentItem(
        source_id=src.id,
        url=f"https://cal.example/{uuid.uuid4().hex}",
        title=topic,
        topic_clusters=[topic],
        embedding=vector,
        fetched_at=datetime.now(UTC),
        word_count=800,
    )
    db_session.add(item)
    await db_session.flush()
    return item


@pytest.mark.asyncio
async def test_thumbs_up_in_the_wizard_lifts_that_topic_on_day_0(client, db_session):
    email = f"cal{uuid.uuid4().hex[:6]}@example.com"
    reg = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "TestPass123!"}
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user_id = user.id
    src = Source(user_id=user_id, url="https://cal.example", feed_url="https://cal.example/f")
    db_session.add(src)
    await db_session.flush()
    compilers = await _item(db_session, src, "compiler optimization passes")
    gardening = await _item(db_session, src, "organic vegetable gardening")
    await db_session.commit()
    compilers_id, gardening_id = compilers.id, gardening.id  # no lazy loads after expire_all
    assert not (
        await db_session.execute(select(InterestNode).where(InterestNode.user_id == user_id))
    ).first()  # the wizard has not created any interests yet

    up = await client.post(
        f"/api/v1/onboarding/calibration/{compilers_id}", json={"rating": 1}, headers=headers
    )
    down = await client.post(
        f"/api/v1/onboarding/calibration/{gardening_id}", json={"rating": -1}, headers=headers
    )
    assert up.json()["clusters_created"] == 1
    assert down.json()["clusters_created"] == 0  # a thumbs-down creates nothing

    db_session.expire_all()
    user = await db_session.get(User, user_id)
    items = [
        await db_session.get(ContentItem, gardening_id),
        await db_session.get(ContentItem, compilers_id),
    ]
    ranked = await rank(user, items, db_session)
    assert ranked[0].item.id == compilers_id
    assert ranked[0].features["semantic"] > ranked[1].features["semantic"]
