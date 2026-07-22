"""Lapsed-user win-back email task (audit 10-5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.models.digest import Digest
from app.models.user import User
from app.workers.tasks import reengagement
from tests.conftest import TestingSessionLocal


@pytest.mark.asyncio
async def test_reengagement_targets_only_lapsed_users(db_session, monkeypatch):
    now = datetime.now(UTC)
    old = now - timedelta(days=40)

    # Lapsed: onboarded 40d ago, last opened digest 30d ago.
    lapsed = User(email="lapsed@example.com", hashed_password="x", onboarding_complete=True)
    # Active: onboarded 40d ago, opened a digest yesterday.
    active = User(email="active@example.com", hashed_password="x", onboarding_complete=True)
    # Email-off: should be skipped regardless.
    emailoff = User(
        email="off@example.com",
        hashed_password="x",
        onboarding_complete=True,
        digest_frequency="in_app_only",
    )
    db_session.add_all([lapsed, active, emailoff])
    await db_session.flush()
    for u in (lapsed, active, emailoff):
        u.created_at = old
    db_session.add(Digest(user_id=lapsed.id, opened=True, generated_at=now - timedelta(days=30)))
    db_session.add(Digest(user_id=active.id, opened=True, generated_at=now - timedelta(days=1)))
    await db_session.commit()

    sent_to: list[str] = []

    async def fake_send(**kwargs):
        sent_to.append(kwargs["to"])
        return True

    monkeypatch.setattr("app.database.AsyncSessionLocal", TestingSessionLocal)
    monkeypatch.setattr(reengagement, "get_settings", reengagement.get_settings)
    monkeypatch.setattr("app.utils.email.send_email", AsyncMock(side_effect=fake_send))
    # Ensure the cooldown key is absent.
    monkeypatch.setattr("app.utils.cache.cache_exists", AsyncMock(return_value=False))
    monkeypatch.setattr("app.utils.cache.cache_set", AsyncMock(return_value=True))

    result = await reengagement._run()

    assert "lapsed@example.com" in sent_to
    assert "active@example.com" not in sent_to
    assert "off@example.com" not in sent_to
    assert result["sent"] == 1
