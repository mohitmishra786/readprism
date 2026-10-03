"""Calibration (CS-03): diverse picks + immediate cluster updates."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.interest_graph import InterestNode
from app.models.source import Source
from app.models.user import User
from app.services.cold_start.calibration import select_calibration_items


def _vec(*vals: float, dim: int = 8) -> list[float]:
    return [vals[i] if i < len(vals) else 0.0 for i in range(dim)]


def test_selection_spreads_across_clusters():
    # Three tight direction groups; selection must cover all three.
    embeddings = [
        _vec(1.0, 0.0),
        _vec(0.99, 0.05),  # group A
        _vec(0.0, 1.0),
        _vec(0.05, 0.99),  # group B
        _vec(-1.0, 0.0),
        _vec(-0.99, -0.05),  # group C
    ]
    picks = select_calibration_items(embeddings, k=3)
    picked_directions = set()
    for p in picks:
        vec = embeddings[p.index]
        if vec[0] > 0.5:
            picked_directions.add("A")
        elif vec[1] > 0.5:
            picked_directions.add("B")
        else:
            picked_directions.add("C")
    assert picked_directions == {"A", "B", "C"}  # diversity assertion


def test_no_embeddings_falls_back_to_recency():
    picks = select_calibration_items([None, None, None], k=2)
    assert [p.index for p in picks] == [0, 1]
    assert all(p.reason == "recency" for p in picks)


def test_respects_k_and_empty_input():
    assert select_calibration_items([], k=5) == []
    picks = select_calibration_items([_vec(1.0, 0.0)] * 50, k=4)
    assert len(picks) <= 4  # identical vectors: only the seed passes 0.35


@pytest.mark.asyncio
async def test_calibration_endpoints(client: AsyncClient, test_user_data: dict, db_session):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()

    src = Source(user_id=user.id, url="https://cal.example/feed")
    db_session.add(src)
    await db_session.flush()
    items = []
    for i, topic in enumerate(["ai", "ai", "systems", "security"]):
        item = ContentItem(
            source_id=src.id,
            url=f"https://cal.example/{i}",
            title=f"cal-{topic}-{i}",
            topic_clusters=[topic],
            fetched_at=datetime.now(UTC),
            embedding=_vec(1.0 if i % 2 else 0.0, 1.0 if i % 3 else 0.0, dim=384),
        )
        items.append(item)
        db_session.add(item)
    db_session.add(InterestNode(user_id=user.id, topic_label="ai", weight=0.5))
    db_session.add(InterestNode(user_id=user.id, topic_label="security", weight=0.5))
    await db_session.commit()

    listed = await client.get("/api/v1/onboarding/calibration", headers=headers)
    assert listed.status_code == 200
    assert 2 <= len(listed.json()) <= 12

    # Rate an ai item up: the ai cluster is reinforced now.
    rated = await client.post(
        f"/api/v1/onboarding/calibration/{items[0].id}",
        json={"rating": 1},
        headers=headers,
    )
    assert rated.status_code == 200
    assert rated.json()["clusters_updated"] == 1

    node = (
        await db_session.execute(
            select(InterestNode).where(
                InterestNode.user_id == user.id, InterestNode.topic_label == "ai"
            )
        )
    ).scalar_one()
    assert node.weight == pytest.approx(0.75)  # 0.5 + 0.25, immediate

    # Rate a security item down: suppressed.
    rated = await client.post(
        f"/api/v1/onboarding/calibration/{items[3].id}",
        json={"rating": -1},
        headers=headers,
    )
    assert rated.json()["clusters_updated"] == 1
    sec = (
        await db_session.execute(
            select(InterestNode).where(
                InterestNode.user_id == user.id, InterestNode.topic_label == "security"
            )
        )
    ).scalar_one()
    assert sec.weight == pytest.approx(0.25)

    bad = await client.post(
        f"/api/v1/onboarding/calibration/{items[0].id}",
        json={"rating": 5},
        headers=headers,
    )
    assert bad.status_code == 422
