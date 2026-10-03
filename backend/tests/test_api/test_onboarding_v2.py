"""Onboarding v2 (CS-01): interest expansion + confirmed topics."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.interest_graph import InterestNode
from app.models.user import User


@pytest.mark.asyncio
async def test_expand_interests_uses_the_llm(client: AsyncClient, test_user_data: dict):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    with patch(
        "app.services.summarization.groq_client.GroqSummarizer.expand_interests",
        return_value=["vector databases", "raft consensus", "ebpf"],
    ):
        result = await client.post(
            "/api/v1/onboarding/expand-interests",
            json={"interest_text": "databases and systems programming"},
            headers=headers,
        )
    assert result.status_code == 200
    assert result.json()["topics"] == ["vector databases", "raft consensus", "ebpf"]


@pytest.mark.asyncio
async def test_expand_interests_falls_back_without_an_llm(
    client: AsyncClient, test_user_data: dict
):
    """LLM-off path: keyword extraction still returns topics (CS-01 accept)."""
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    with patch(
        "app.services.summarization.groq_client.GroqSummarizer.expand_interests",
        side_effect=RuntimeError("no key"),
    ):
        result = await client.post(
            "/api/v1/onboarding/expand-interests",
            json={"interest_text": "machine learning and distributed systems"},
            headers=headers,
        )
    assert result.status_code == 200
    topics = result.json()["topics"]
    assert topics, "keyword fallback must produce topics"
    assert any("machine learning" in t for t in topics)


@pytest.mark.asyncio
async def test_confirmed_topics_become_the_initial_clusters(
    client: AsyncClient, test_user_data: dict, db_session
):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()

    with (
        patch("app.services.cold_start.onboarding.GroqSummarizer") as mock_groq,
        patch(
            "app.workers.tasks.update_interest_graph.update_interest_graph_for_interaction.delay"
        ),
    ):
        mock_groq.return_value.extract_topics.return_value = ["should-not-appear"]
        result = await client.post(
            "/api/v1/onboarding",
            json={
                "interest_text": "whatever",
                "sample_ratings": [],
                "confirmed_topics": ["vector databases", "raft consensus", "ebpf"],
            },
            headers=headers,
        )
    assert result.status_code == 200

    nodes = {
        n.topic_label: n.weight
        for n in (
            await db_session.execute(select(InterestNode).where(InterestNode.user_id == user.id))
        ).scalars()
    }
    assert set(nodes) == {"vector databases", "raft consensus", "ebpf"}
    # Confirmed interests start above neutral with a prior weight.
    assert all(w == 0.6 for w in nodes.values())
    await db_session.refresh(user)
    assert user.onboarding_complete is True
