"""Integration test for full-text retention pruning (audit 08-3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.content import ContentItem
from app.workers.tasks import prune_content
from tests.conftest import TestingSessionLocal


@pytest.mark.asyncio
async def test_prune_truncates_old_full_text_only(db_session, monkeypatch):
    long_text = "x" * 2000
    old = ContentItem(
        url="https://example.com/old",
        title="Old",
        full_text=long_text,
        fetched_at=datetime.now(UTC) - timedelta(days=200),
    )
    recent = ContentItem(
        url="https://example.com/recent",
        title="Recent",
        full_text=long_text,
        fetched_at=datetime.now(UTC) - timedelta(days=2),
    )
    db_session.add_all([old, recent])
    await db_session.commit()
    old_id, recent_id = old.id, recent.id

    # Point the task's session factory at the test engine/session.
    monkeypatch.setattr("app.database.AsyncSessionLocal", TestingSessionLocal)
    monkeypatch.setattr(prune_content.get_settings(), "content_full_text_retention_days", 90)
    monkeypatch.setattr(prune_content.get_settings(), "content_excerpt_chars", 500)

    result = await prune_content._prune_full_text_async()
    assert result["status"] == "ok"
    assert result["pruned"] >= 1

    # Re-read from the DB (the task committed on its own session).
    await db_session.rollback()
    old_row = (
        await db_session.execute(select(ContentItem).where(ContentItem.id == old_id))
    ).scalar_one()
    recent_row = (
        await db_session.execute(select(ContentItem).where(ContentItem.id == recent_id))
    ).scalar_one()
    await db_session.refresh(old_row)
    await db_session.refresh(recent_row)

    assert len(old_row.full_text) == 500  # truncated to excerpt
    assert len(recent_row.full_text) == 2000  # untouched


@pytest.mark.asyncio
async def test_prune_disabled_when_retention_zero(db_session, monkeypatch):
    monkeypatch.setattr("app.database.AsyncSessionLocal", TestingSessionLocal)
    monkeypatch.setattr(prune_content.get_settings(), "content_full_text_retention_days", 0)
    result = await prune_content._prune_full_text_async()
    assert result["status"] == "disabled"
