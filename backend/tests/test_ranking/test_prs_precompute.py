"""Smoke test for the periodic PRS pre-compute batch.

The full precompute touches many subsystems; this test exercises the parts
that matter for correctness of the *batch* logic: the short-circuit when
there are no users or items, and that tasks are enqueued only for missing
PRS scores. DB access is mocked.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.tasks import compute_prs as prs_task


@pytest.mark.asyncio
async def test_precompute_short_circuits_when_no_active_users():
    """With zero active users, nothing is queued and we get a clean summary."""
    fake_session = AsyncMock()

    # users_result.fetchall() -> []
    users_result = MagicMock()
    users_result.all.return_value = []
    fake_session.execute = AsyncMock(return_value=users_result)

    with patch("app.database.AsyncSessionLocal") as session_ctx:
        session_ctx.return_value.__aenter__ = AsyncMock(return_value=fake_session)
        session_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await prs_task._precompute_batch_async()

    assert result["queued"] == 0
    assert result["users"] == 0


@pytest.mark.asyncio
async def test_precompute_short_circuits_when_no_recent_content():
    """With active users but zero recent items, nothing is queued."""
    fake_session = AsyncMock()

    users_result = MagicMock()
    users_result.all.return_value = [(uuid.uuid4(),)]
    content_result = MagicMock()
    content_result.all.return_value = []  # no recent content

    fake_session.execute = AsyncMock(side_effect=[users_result, content_result])

    with patch("app.database.AsyncSessionLocal") as session_ctx:
        session_ctx.return_value.__aenter__ = AsyncMock(return_value=fake_session)
        session_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await prs_task._precompute_batch_async()

    assert result["queued"] == 0
    assert result["users"] == 1
    assert result["items"] == 0


@pytest.mark.asyncio
async def test_precompute_enqueues_missing_prs_only():
    """An item with no existing PRS score is enqueued; one that already has a score is skipped."""
    user_id = uuid.uuid4()
    content_with_score = uuid.uuid4()
    content_without_score = uuid.uuid4()

    fake_session = AsyncMock()

    users_result = MagicMock()
    users_result.all.return_value = [(user_id,)]
    content_result = MagicMock()
    content_result.all.return_value = [(content_with_score,), (content_without_score,)]

    # Per-item existence checks: first item has a score (scalar_one_or_none != None),
    # second does not (returns None).
    has_score_result = MagicMock()
    has_score_result.scalar_one_or_none.return_value = uuid.uuid4()
    no_score_result = MagicMock()
    no_score_result.scalar_one_or_none.return_value = None

    fake_session.execute = AsyncMock(
        side_effect=[users_result, content_result, has_score_result, no_score_result]
    )

    enqueued: list[tuple[str, str]] = []

    with patch("app.database.AsyncSessionLocal") as session_ctx, patch.object(
        prs_task.compute_prs_for_user_item, "delay", lambda u, c: enqueued.append((u, c))
    ):
        session_ctx.return_value.__aenter__ = AsyncMock(return_value=fake_session)
        session_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await prs_task._precompute_batch_async()

    # Only the item without a score should be enqueued.
    assert result["queued"] == 1
    assert len(enqueued) == 1
    assert enqueued[0][0] == str(user_id)
    assert enqueued[0][1] == str(content_without_score)
