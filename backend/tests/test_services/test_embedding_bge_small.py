"""Tests for BAAI/bge-small-en-v1.5 spec, selection matrix, online re-embed and metrics (#244)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.content import ContentItem
from app.models.user import User
from app.services.embeddings.reembed import (
    REDIS_CURSOR_KEY,
    get_reembed_cursor,
    reembed_batch,
    set_reembed_cursor,
)
from app.services.embeddings.registry import (
    BGE_SMALL,
    BGE_SMALL_QUERY_PREFIX,
    BGE_SMALL_SHORT,
    MINILM,
    NOMIC,
    active_spec,
    same_model,
    spec_for,
)
from app.services.ranking.ranker import HistoryRow, UserRankingState, score_candidates
from app.utils.cache import cache_get, cache_set
from app.workers.tasks.compute_embeddings import _reembed_outdated_items_async


class FakeEncoder:
    """Fake encoder that returns deterministic vectors without downloading weights."""

    def __init__(self, dim: int = 384) -> None:
        self.dimension = dim
        self._fixed = [0.1] * dim

    async def encode_batch_cached(self, texts: list[str]) -> list[list[float]]:
        return [self._fixed for _ in texts]

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._fixed for _ in texts]


def test_bge_small_registry_spec_and_prefixes():
    spec = spec_for(BGE_SMALL)
    assert spec.name == BGE_SMALL
    assert spec.dim == 384
    assert spec.prefix_query == BGE_SMALL_QUERY_PREFIX
    assert spec.prefix_document == ""
    assert spec.max_tokens == 512

    # Accept short name too
    short_spec = spec_for(BGE_SMALL_SHORT)
    assert short_spec.name == BGE_SMALL
    assert short_spec.dim == 384
    assert short_spec.prefix_query == BGE_SMALL_QUERY_PREFIX


def test_selection_matrix():
    # 1. Default settings (MiniLM, cutover False)
    assert active_spec(model=MINILM, cutover=False).name == MINILM

    # 2. Cutover False keeps MiniLM even if bge-small is configured
    assert active_spec(model=BGE_SMALL_SHORT, cutover=False).name == MINILM
    assert active_spec(model=BGE_SMALL, cutover=False).name == MINILM

    # 3. Cutover True with bge-small activates bge-small
    assert active_spec(model=BGE_SMALL_SHORT, cutover=True).name == BGE_SMALL
    assert active_spec(model=BGE_SMALL, cutover=True).name == BGE_SMALL

    # 4. Nomic (768-d) is rejected while column is 384-d, falls back to MiniLM
    assert active_spec(model=NOMIC, cutover=True).name == MINILM
    assert active_spec(model=NOMIC, cutover=False).name == MINILM


@pytest.mark.asyncio
async def test_reembed_batch_and_redis_cursor(db_session, monkeypatch):
    """Test reembed_batch updates rows, commits, and tracks cursor in Redis."""
    target_spec = spec_for(BGE_SMALL)
    fake_enc = FakeEncoder(dim=target_spec.dim)

    # Clean cursor
    await set_reembed_cursor(None)

    # Create 3 items with MiniLM
    items = [
        ContentItem(
            id=uuid.uuid4(),
            url=f"https://example.com/test/{i}",
            title=f"Article {i}",
            full_text=f"Text for article {i}",
            embedding=[0.01] * 384,
            embedding_model=MINILM,
            embedding_dim=384,
            embedding_version="1",
        )
        for i in range(3)
    ]
    items.sort(key=lambda x: x.id)
    db_session.add_all(items)
    await db_session.commit()

    # Re-embed in batch of 2
    res1 = await reembed_batch(
        session=db_session,
        active=target_spec,
        batch_size=2,
        cursor=None,
        encoder=fake_enc,
    )
    assert res1["reembedded"] == 2
    assert res1["next_cursor"] == str(items[1].id)
    assert not res1["done"]

    # Cursor should be saved in Redis
    saved_cursor = await get_reembed_cursor()
    assert saved_cursor == str(items[1].id)

    # Check DB status
    r1 = await db_session.get(ContentItem, items[0].id)
    assert r1.embedding_model == BGE_SMALL
    r3 = await db_session.get(ContentItem, items[2].id)
    assert r3.embedding_model == MINILM

    # Second batch
    res2 = await reembed_batch(
        session=db_session,
        active=target_spec,
        batch_size=2,
        cursor=saved_cursor,
        encoder=fake_enc,
    )
    assert res2["reembedded"] == 1
    assert res2["done"]

    # Verify all updated
    for item in items:
        refreshed = await db_session.get(ContentItem, item.id)
        assert refreshed.embedding_model == BGE_SMALL


@pytest.mark.asyncio
async def test_reembed_resumes_after_crash(db_session, monkeypatch):
    """Simulate a crash mid-migration and verify task resumes from Redis cursor."""
    target_spec = spec_for(BGE_SMALL)
    fake_enc = FakeEncoder(dim=target_spec.dim)

    await set_reembed_cursor(None)

    # Create 4 items
    items = [
        ContentItem(
            id=uuid.uuid4(),
            url=f"https://example.com/crash-test/{i}",
            title=f"Crash test {i}",
            full_text=f"Content {i}",
            embedding=[0.02] * 384,
            embedding_model=MINILM,
            embedding_dim=384,
            embedding_version="1",
        )
        for i in range(4)
    ]
    items.sort(key=lambda x: x.id)
    db_session.add_all(items)
    await db_session.commit()

    # Batch 1 succeeds (size 2)
    res1 = await reembed_batch(
        session=db_session,
        active=target_spec,
        batch_size=2,
        cursor=None,
        encoder=fake_enc,
    )
    assert res1["reembedded"] == 2
    cursor_after_b1 = res1["next_cursor"]
    assert cursor_after_b1 == str(items[1].id)

    # Simulate crash before Batch 2 finishes: cursor is still cursor_after_b1
    # Now run resuming from that cursor
    res_resume = await reembed_batch(
        session=db_session,
        active=target_spec,
        batch_size=2,
        cursor=cursor_after_b1,
        encoder=fake_enc,
    )
    assert res_resume["reembedded"] == 2
    assert res_resume["next_cursor"] == str(items[3].id)

    # All items are now target model
    for item in items:
        refreshed = await db_session.get(ContentItem, item.id)
        assert refreshed.embedding_model == BGE_SMALL


def test_half_migrated_table_never_mixes_models_in_one_query(monkeypatch):
    """Verify ranking rejects vectors from a different model during cutover."""
    from app.config import get_settings
    from app.services.ranking.contract import SIGNALS
    from app.services.ranking.ranker import FeedState, UserRankingState

    bge_spec = spec_for(BGE_SMALL)
    minilm_spec = spec_for(MINILM)

    # same_model rules
    assert same_model(BGE_SMALL, 384, bge_spec)
    assert same_model(BGE_SMALL_SHORT, 384, bge_spec)
    assert not same_model(MINILM, 384, bge_spec)
    assert not same_model(None, 384, bge_spec)  # unlabeled does not match bge-small
    assert same_model(MINILM, 384, minilm_spec)
    assert same_model(None, 384, minilm_spec)  # legacy default matches MiniLM

    # When active is bge-small:
    # Candidate A has bge-small embedding
    cand_a = ContentItem(
        id=uuid.uuid4(),
        url="https://x/a",
        title="BGE Article",
        embedding=[0.05] * 384,
        embedding_model=BGE_SMALL,
        embedding_dim=384,
    )
    # Candidate B has legacy MiniLM embedding (not yet migrated)
    cand_b = ContentItem(
        id=uuid.uuid4(),
        url="https://x/b",
        title="MiniLM Article",
        embedding=[0.05] * 384,
        embedding_model=MINILM,
        embedding_dim=384,
    )

    state = UserRankingState(
        user_id=uuid.uuid4(),
        weights={s: 1.0 / len(SIGNALS) for s in SIGNALS},
        history=[],
        interests=[],
        bridges=[],
        feeds={},
        source_feed_key={},
        prefers_fresh=False,
        novelty_target=0.2,
    )

    s = get_settings()
    monkeypatch.setattr(s, "embedding_model", BGE_SMALL)
    monkeypatch.setattr(s, "embedding_cutover_enabled", True)

    scored = score_candidates(state, [cand_a, cand_b])
    assert len(scored) == 2


@pytest.mark.asyncio
async def test_metrics_embeddings_endpoint(client: AsyncClient, db_session, monkeypatch):
    """GET /api/v1/metrics/embeddings returns counts per model and percent done."""
    from app.api import metrics as metrics_api
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(metrics_api.settings, "metrics_token", "secret-test-token")
    monkeypatch.setattr(metrics_api.settings, "app_env", "production")
    monkeypatch.setattr(s, "metrics_token", "secret-test-token")
    monkeypatch.setattr(s, "embedding_model", BGE_SMALL)
    monkeypatch.setattr(s, "embedding_cutover_enabled", True)

    # Insert items: 1 with bge-small, 1 with MiniLM
    item_bge = ContentItem(
        id=uuid.uuid4(),
        url="https://example.com/bge",
        title="BGE Item",
        embedding=[0.01] * 384,
        embedding_model=BGE_SMALL,
        embedding_dim=384,
    )
    item_mini = ContentItem(
        id=uuid.uuid4(),
        url="https://example.com/mini",
        title="Mini Item",
        embedding=[0.02] * 384,
        embedding_model=MINILM,
        embedding_dim=384,
    )
    db_session.add_all([item_bge, item_mini])
    await db_session.commit()

    # 1. Unauthorized without token
    res_unauth = await client.get("/api/v1/metrics/embeddings")
    assert res_unauth.status_code == 401

    # 2. Authorized with metrics token
    res = await client.get(
        "/api/v1/metrics/embeddings",
        headers={"X-Metrics-Token": "secret-test-token"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["active_model"] == BGE_SMALL
    assert data["active_dim"] == 384
    assert data["cutover_enabled"] is True
    assert BGE_SMALL in data["counts_by_model"]
    assert MINILM in data["counts_by_model"]
    assert data["total_embedded"] >= 2
    assert 0.0 <= data["percent_done"] <= 100.0


# ---------------------------------------------------------------- review fixes


def _set_active(monkeypatch, model: str, cutover: bool) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "embedding_model", model)
    monkeypatch.setattr(get_settings(), "embedding_cutover_enabled", cutover)


@pytest.mark.asyncio
async def test_outdated_rule_counts_aliases_and_legacy_rows_as_current(db_session):
    """Nothing is re-encoded for nothing: aliases of the active model and
    unstamped rows (legacy MiniLM) are current while MiniLM is active."""
    from app.services.embeddings.reembed import outdated

    tag = uuid.uuid4().hex[:8]
    rows = {
        "minilm": MINILM,
        "alias": "sentence-transformers/all-MiniLM-L6-v2",
        "legacy": None,
        "bge": BGE_SMALL,
    }
    for name, model in rows.items():
        db_session.add(
            ContentItem(
                url=f"https://example.com/{tag}/{name}",
                title=f"{tag}-{name}",
                embedding=[0.01] * 384,
                embedding_model=model,
            )
        )
    await db_session.commit()

    async def stale(active_name: str) -> set[str]:
        active = spec_for(active_name)
        found = await db_session.execute(
            select(ContentItem.title).where(
                ContentItem.title.like(f"{tag}-%"), outdated(ContentItem.embedding_model, active)
            )
        )
        return {t.split("-", 1)[1] for t in found.scalars()}

    assert await stale(MINILM) == {"bge"}
    assert await stale(BGE_SMALL) == {"minilm", "alias", "legacy"}


@pytest.mark.asyncio
async def test_interest_topics_are_stamped_and_reembedded(db_session, monkeypatch):
    """Topic vectors are compared with item vectors in ranking, so they carry
    their model and move with a switch."""
    from app.models.interest_graph import InterestNode
    from app.services.embeddings.reembed import INTEREST_CURSOR_KEY, reembed_interest_batch

    user = User(email=f"it{uuid.uuid4().hex[:8]}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    _set_active(monkeypatch, MINILM, False)
    node = InterestNode(user_id=user.id, topic_label="databases", topic_embedding=[0.2] * 384)
    db_session.add(node)
    await db_session.commit()
    assert node.embedding_model == MINILM  # stamped by the listener

    _set_active(monkeypatch, BGE_SMALL_SHORT, True)
    from app.utils.cache import get_redis

    await get_redis().delete(INTEREST_CURSOR_KEY)
    result = await reembed_interest_batch(
        db_session, spec_for(BGE_SMALL), batch_size=500, encoder=FakeEncoder()
    )
    assert result["reembedded"] >= 1
    await db_session.refresh(node)
    assert node.embedding_model == BGE_SMALL
    assert list(node.topic_embedding)[:2] == pytest.approx([0.1, 0.1])

    # A later write by any call site is stamped with whatever model is active.
    _set_active(monkeypatch, MINILM, False)
    node.topic_embedding = [0.3] * 384
    db_session.add(node)
    await db_session.commit()
    assert node.embedding_model == MINILM


@pytest.mark.asyncio
async def test_task_reembeds_items_then_topics(db_session, monkeypatch):
    """The scheduled task finishes items, then interest topics, and reports both."""
    from app.models.interest_graph import InterestNode
    from app.services.embeddings.reembed import INTEREST_CURSOR_KEY
    from app.utils.cache import get_redis
    from tests.conftest import TestingSessionLocal

    _set_active(monkeypatch, MINILM, False)
    user = User(email=f"tk{uuid.uuid4().hex[:8]}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        InterestNode(user_id=user.id, topic_label="compilers", topic_embedding=[0.2] * 384)
    )
    db_session.add(
        ContentItem(
            url=f"https://example.com/task/{uuid.uuid4().hex}",
            title="Old vector",
            full_text="Body",
            embedding=[0.01] * 384,
            embedding_model=MINILM,
        )
    )
    await db_session.commit()

    _set_active(monkeypatch, BGE_SMALL_SHORT, True)
    await set_reembed_cursor(None)
    await get_redis().delete(INTEREST_CURSOR_KEY)
    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.utils.embeddings.get_embedding_service", return_value=FakeEncoder()),
    ):
        report = await _reembed_outdated_items_async(batch_size=1000)
        assert report["total_reembedded"] >= 1
        assert report["topics_reembedded"] >= 1
        assert report["done"] is True

        # Budget: with max_batches=1 the task stops after one batch.
        partial = await _reembed_outdated_items_async(batch_size=1000, max_batches=1)
        assert partial["batches_run"] == 1
