"""First-digest quality gate (CS-05): pure check + a persona end-to-end run."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.digest import DigestItem
from app.models.source import Source
from app.models.user import User
from app.services.cold_start.first_digest import first_digest_quality


def test_gate_passes_a_healthy_digest():
    items = [
        {
            "url": f"https://x/{i}",
            "topic_clusters": [f"t{i}"],
            "origin": "followed",
            "summary": "ok",
        }
        for i in range(5)
    ]
    items[0]["origin"] = "discovery"
    report = first_digest_quality(items)
    assert report.passed, report.reasons()


def test_gate_fails_each_dimension():
    base = {"url": "", "topic_clusters": [], "origin": "followed", "summary": ""}
    # 2 items, no clusters, no discovery, no summaries, duplicate URL.
    report = first_digest_quality(
        [
            {**base, "url": "https://dup"},
            {**base, "url": "https://dup"},
        ]
    )
    assert not report.passed
    reasons = " ".join(report.reasons())
    assert "items" in reasons and "clusters" in reasons and "discovery" in reasons
    assert "duplicates" in reasons and "summaries" in reasons


@pytest.mark.asyncio
async def test_persona_first_digest_meets_the_gate(
    client: AsyncClient, test_user_data: dict, db_session
):
    """CS-05 persona e2e: a fresh user's first real build_digest output passes.

    Persona: follows a source with 6 distinct-topic summarized articles; a
    second user's public discovery item exists in the window.
    """
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    other = User(email="cs5-discovery@example.com", hashed_password="x")
    db_session.add(other)
    await db_session.flush()

    src = Source(user_id=user.id, url="https://cs5.example/feed")
    src2 = Source(user_id=user.id, url="https://cs5b.example/feed")
    pub = Source(user_id=other.id, url="https://cs5pub.example/feed")
    db_session.add_all([src, src2, pub])
    await db_session.flush()

    now = datetime.now(UTC)
    # Two sources so the per-source cap (3) does not shrink the digest.
    for i in range(6):
        db_session.add(
            ContentItem(
                source_id=(src if i < 3 else src2).id,
                url=f"https://cs5.example/{i}",
                title=f"persona-{i}",
                topic_clusters=[f"topic{i}"],
                summary_brief=f"A solid summary {i}.",
                fetched_at=now,
                word_count=800,
            )
        )
    db_session.add(
        ContentItem(
            source_id=pub.id,
            url="https://cs5pub.example/d",
            title="discovery-item",
            topic_clusters=["discovery-topic"],
            summary_brief="A discovery summary.",
            origin="discovery",
            fetched_at=now,
        )
    )
    await db_session.commit()

    from app.services.digest.builder import build_digest

    with (
        patch(
            "app.services.summarization.groq_client.GroqSummarizer",
            side_effect=Exception("llm off"),
        ),
        patch(
            "app.workers.tasks.update_interest_graph.update_interest_graph_for_interaction.delay"
        ),
    ):
        digest = await build_digest(user, db_session)
    await db_session.commit()

    rows = (
        (await db_session.execute(select(DigestItem).where(DigestItem.digest_id == digest.id)))
        .scalars()
        .all()
    )
    content_rows = (
        (
            await db_session.execute(
                select(ContentItem).where(ContentItem.id.in_([r.content_item_id for r in rows]))
            )
        )
        .scalars()
        .all()
    )
    by_id = {c.id: c for c in content_rows}

    items = [
        {
            "url": by_id[r.content_item_id].url,
            "topic_clusters": by_id[r.content_item_id].topic_clusters or [],
            "origin": by_id[r.content_item_id].origin,
            "summary": by_id[r.content_item_id].summary_brief
            or (r.signal_breakdown or {}).get("story_briefing", ""),
        }
        for r in rows
    ]
    report = first_digest_quality(items)
    assert report.passed, report.reasons()
