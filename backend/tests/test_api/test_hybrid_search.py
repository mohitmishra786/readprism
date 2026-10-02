"""Hybrid search (UX-11): RRF fusion, FTS relevance, filters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.user import User
from app.services.embeddings.registry import hash_embed
from app.services.search.hybrid import rrf_fuse


def test_rrf_prefers_items_present_in_both_lists():
    fused = rrf_fuse(["a", "b", "c"], ["b", "d"])
    assert fused[0] == "b"  # in both lists
    assert set(fused) == {"a", "b", "c", "d"}


def test_rrf_respects_rank_within_lists():
    fused = rrf_fuse(["a", "b"], ["c"])
    # a: 1/61 (fts rank1). c: 1/61 (vector rank1). Tie -> first seen (a) wins;
    # b only has the rank-2 contribution.
    assert fused == ["a", "c", "b"]


def test_rrf_higher_rank_scores_higher():
    fused = rrf_fuse(["a", "b"], ["b", "a"])
    # a: 1/61 + 1/62 ; b: 1/62 + 1/61 — exact tie, first seen (a) wins.
    assert fused[0] == "a"


@pytest.mark.asyncio
async def test_search_endpoint_finds_and_filters(
    client: AsyncClient, test_user_data: dict, db_session
):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()

    from app.models.source import Source

    src = Source(user_id=user.id, url="https://search.example/feed")
    other_src = Source(user_id=user.id, url="https://search-other.example/feed")
    db_session.add_all([src, other_src])
    await db_session.flush()

    now = datetime.now(UTC)
    on_topic = ContentItem(
        source_id=src.id,
        url="https://search.example/1",
        title="Postgres full-text search deep dive",
        # Three query lexemes matched (postgres, search, tsvector in the
        # B-weighted headline) — strictly stronger than any 2-lexeme title,
        # so ts_rank ordering is deterministic (measured: extra lexeme beats
        # position effects).
        summary_headline="How tsvector and websearch_to_tsquery work",
        fetched_at=now,
    )
    other_topic = ContentItem(
        source_id=src.id,
        url="https://search.example/2",
        title="Sourdough starter guide",
        summary_headline="Flour, water, patience",
        fetched_at=now,
    )
    old_item = ContentItem(
        source_id=src.id,
        url="https://search.example/3",
        title="Postgres year in review",
        summary_headline="A look back",  # only ONE query term matches
        fetched_at=now - timedelta(days=400),
    )
    other_source_item = ContentItem(
        source_id=other_src.id,
        url="https://search-other.example/4",
        title="Postgres search on a muted source",
        fetched_at=now,
    )
    db_session.add_all([on_topic, other_topic, old_item, other_source_item])
    await db_session.commit()

    result = await client.get(
        "/api/v1/search", params={"q": "postgres search tsvector"}, headers=headers
    )
    assert result.status_code == 200
    hits = result.json()["hits"]
    titles = [h["title"] for h in hits]
    # Relevance: the deep dive (3 matched lexemes) ranks first; the sourdough
    # article must not appear at all.
    assert titles[0] == "Postgres full-text search deep dive"
    assert all("Sourdough" not in t for t in titles)

    # Filter: since_days excludes the year-old item.
    result = await client.get(
        "/api/v1/search",
        params={"q": "postgres search tsvector", "since_days": 30},
        headers=headers,
    )
    titles = [h["title"] for h in result.json()["hits"]]
    assert "Postgres year in review" not in titles

    # Filter: source_id restricts the leg.
    result = await client.get(
        "/api/v1/search",
        params={"q": "postgres search", "source_id": str(other_src.id)},
        headers=headers,
    )
    titles = [h["title"] for h in result.json()["hits"]]
    assert titles == ["Postgres search on a muted source"]


@pytest.mark.asyncio
async def test_vector_leg_participates_with_matching_model(
    client: AsyncClient, test_user_data: dict, db_session
):
    """An item embedded by the active spec can be found semantically."""
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()

    from app.models.source import Source

    src = Source(user_id=user.id, url="https://vec.example/feed")
    db_session.add(src)
    await db_session.flush()
    item = ContentItem(
        source_id=src.id,
        url="https://vec.example/1",
        title="Totally unusual title xyzzy",
        fetched_at=datetime.now(UTC),
    )
    item.embedding_model = "hash-mini"  # set below via registry name instead
    await db_session.flush()

    from app.services.embeddings.registry import active_spec, encode_with_spec

    spec = active_spec(model="all-MiniLM-L6-v2", cutover=False)
    item.embedding_model = spec.name
    item.embedding_dim = spec.dim
    item.embedding = encode_with_spec("Totally unusual title xyzzy", spec, query=False)
    db_session.add(item)
    await db_session.commit()

    result = await client.get("/api/v1/search", params={"q": "xyzzy"}, headers=headers)
    assert result.status_code == 200
    assert any(h["title"] == "Totally unusual title xyzzy" for h in result.json()["hits"])
