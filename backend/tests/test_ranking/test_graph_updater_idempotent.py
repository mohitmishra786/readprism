"""Interest-graph updates are idempotent per read (#105).

The reader flushes telemetry every 20 s and each flush enqueues a graph
update; a long read used to reinforce the same nodes, edges and trust ~30x.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.interest_graph import InterestEdge, InterestNode
from app.models.source import Source
from app.models.user import User
from app.services.interest_graph.updater import TRUST_LEARN_RATE, update_from_interaction
from tests.conftest import TestingSessionLocal


class _FakeEmbeddings:
    async def encode_batch_cached(self, texts):
        return [[float(i + 1)] + [0.0] * 383 for i, _ in enumerate(texts)]


@pytest.fixture(autouse=True)
def _fake_embeddings():
    with patch(
        "app.services.interest_graph.updater.get_embedding_service", return_value=_FakeEmbeddings()
    ):
        yield


async def _setup(session):
    user = User(id=uuid.uuid4(), email=f"g{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    session.add(user)
    await session.flush()
    source = Source(user_id=user.id, url="https://blog.example.com", trust_weight=0.5)
    session.add(source)
    await session.flush()
    content = ContentItem(
        source_id=source.id,
        url=f"https://blog.example.com/{uuid.uuid4().hex}",
        title="Rust compilers",
        topic_clusters=["rust", "compilers", "llvm"],
    )
    session.add(content)
    await session.flush()
    interaction = UserContentInteraction(
        user_id=user.id,
        content_item_id=content.id,
        read_completion_pct=0.9,
        time_on_page_seconds=300,
    )
    session.add(interaction)
    await session.flush()
    return user, source, content, interaction


async def _snapshot(session, user_id, source_id):
    nodes = {
        n.topic_label: (round(n.weight, 9), n.reinforcement_count)
        for n in (
            await session.execute(select(InterestNode).where(InterestNode.user_id == user_id))
        ).scalars()
    }
    edges = sorted(
        e.co_occurrence_count
        for e in (
            await session.execute(select(InterestEdge).where(InterestEdge.user_id == user_id))
        ).scalars()
    )
    trust = (
        await session.execute(select(Source.trust_weight).where(Source.id == source_id))
    ).scalar_one()
    return nodes, edges, round(trust, 9)


@pytest.mark.asyncio
async def test_repeated_flushes_of_one_read_apply_once(db_session):
    user, source, content, interaction = await _setup(db_session)

    assert await update_from_interaction(interaction, content, db_session) is True
    once = await _snapshot(db_session, user.id, source.id)
    for _ in range(9):
        assert await update_from_interaction(interaction, content, db_session) is False
    ten = await _snapshot(db_session, user.id, source.id)

    assert ten == once
    nodes, edges, trust = once
    assert all(count == 1 for _, count in nodes.values())
    assert edges == [1, 1, 1]  # three topics -> three pairs, each counted once
    assert trust == pytest.approx(0.5 + TRUST_LEARN_RATE * 0.8)


@pytest.mark.asyncio
async def test_growing_read_applies_only_the_increase(db_session):
    user, source, content, interaction = await _setup(db_session)
    interaction.read_completion_pct = 0.6  # partial read: signal 0.4
    await update_from_interaction(interaction, content, db_session)
    interaction.read_completion_pct = 0.95  # finished: signal 0.8
    await update_from_interaction(interaction, content, db_session)

    nodes, edges, trust = await _snapshot(db_session, user.id, source.id)
    # Same end state as a single full read: 0.1 start + 0.8 * 0.1
    assert all(weight == pytest.approx(0.18) for weight, _ in nodes.values())
    assert all(count == 1 for _, count in nodes.values())
    assert edges == [1, 1, 1]
    assert trust == pytest.approx(0.5 + TRUST_LEARN_RATE * 0.8)


@pytest.mark.asyncio
async def test_changed_rating_applies_the_difference_once(db_session):
    user, source, content, interaction = await _setup(db_session)
    interaction.explicit_rating = 1  # signal 1.0
    await update_from_interaction(interaction, content, db_session)
    interaction.explicit_rating = -1  # signal -0.8
    await update_from_interaction(interaction, content, db_session)
    await update_from_interaction(interaction, content, db_session)

    nodes, _, trust = await _snapshot(db_session, user.id, source.id)
    # 0.1 + 0.1 (thumbs up), then -1.8 * 0.1 -> clamped at 0
    assert all(weight == pytest.approx(0.02) for weight, _ in nodes.values())
    assert trust == pytest.approx(0.5 + TRUST_LEARN_RATE * -0.8)
    assert interaction.graph_signal_applied == pytest.approx(-0.8)


@pytest.mark.asyncio
async def test_score_only_rows_do_not_count_toward_the_learning_threshold(db_session):
    from app.workers.tasks import update_interest_graph as task

    user, source, content, interaction = await _setup(db_session)
    interaction.opened_at = None
    for i in range(30):  # precompute/digest rows: a score, never opened
        item = ContentItem(source_id=source.id, url=f"https://blog.example.com/p{i}", title=f"P{i}")
        db_session.add(item)
        await db_session.flush()
        db_session.add(
            UserContentInteraction(user_id=user.id, content_item_id=item.id, prs_score=0.5)
        )
    await db_session.commit()

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch.object(task, "_enqueue_meta_weights_update") as enqueue,
    ):
        await task._update_graph_async(interaction.id)

    enqueue.assert_not_called()
