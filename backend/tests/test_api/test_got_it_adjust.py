"""Post-read 'More / Less' (#228) moves the item's topic in the interest graph."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.interest_graph import InterestNode
from app.models.user import User


@pytest.mark.asyncio
async def test_more_and_less_adjust_the_topic(client, db_session):
    email = f"gi{uuid.uuid4().hex[:6]}@example.com"
    reg = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "TestPass123!"}
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user_id = user.id  # read before expire_all (no lazy loads in async)
    db_session.add(InterestNode(user_id=user_id, topic_label="compilers", weight=0.4))
    await db_session.commit()

    async def weight() -> float:
        db_session.expire_all()
        node = (
            await db_session.execute(
                select(InterestNode).where(
                    InterestNode.user_id == user_id, InterestNode.topic_label == "compilers"
                )
            )
        ).scalar_one()
        return node.weight

    more = await client.post(
        "/api/v1/feedback/adjust-interests",
        json={"topic": "compilers", "action": "boost"},
        headers=headers,
    )
    assert more.status_code == 200
    assert await weight() == pytest.approx(0.7)

    less = await client.post(
        "/api/v1/feedback/adjust-interests",
        json={"topic": "compilers", "action": "suppress"},
        headers=headers,
    )
    assert less.status_code == 200
    assert await weight() == pytest.approx(0.4)
