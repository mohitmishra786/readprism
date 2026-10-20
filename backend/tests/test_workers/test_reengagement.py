"""Gentle win-back and pause flow (#238)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from urllib.parse import parse_qs, urlparse

import pytest

from app.models.digest import Digest
from app.models.user import User
from app.workers.tasks import reengagement
from app.workers.tasks.reengagement import ASK, FINAL, LIGHT, due_stage
from tests.conftest import TestingSessionLocal

NOW = datetime(2026, 10, 20, 16, tzinfo=UTC)


@pytest.mark.parametrize(
    ("days", "stage", "sent_days_ago", "expected"),
    [
        (2, 0, None, None),  # not lapsed yet
        (3, 0, None, LIGHT),  # day 3: lighter digest
        (5, LIGHT, 2, None),  # already sent this stage
        (10, LIGHT, 7, ASK),  # day 10: pause or weekly?
        (10, LIGHT, 1, None),  # due, but within the 3-day gap
        (30, ASK, 20, FINAL),  # day 30: last note
        (90, FINAL, 60, None),  # stopped for good
        (45, 0, None, FINAL),  # missed stages are skipped, never sent together
    ],
)
def test_each_transition(days, stage, sent_days_ago, expected):
    last_sent = NOW - timedelta(days=sent_days_ago) if sent_days_ago is not None else None
    assert (
        due_stage(days_inactive=days, current_stage=stage, last_sent=last_sent, now=NOW) == expected
    )


async def _user(db_session, *, last_open_days_ago=None, created_days_ago=60, **kw):
    user = User(
        email=f"wb{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="x",
        onboarding_complete=True,
        email_verified_at=NOW - timedelta(days=90),
        **kw,
    )
    db_session.add(user)
    await db_session.flush()
    user.created_at = NOW - timedelta(days=created_days_ago)
    if last_open_days_ago is not None:
        db_session.add(
            Digest(
                user_id=user.id, opened=True, generated_at=NOW - timedelta(days=last_open_days_ago)
            )
        )
    await db_session.commit()
    return user


async def _run(now=NOW):
    from unittest.mock import patch

    outbox: list[dict] = []

    async def fake_send(**kwargs):
        outbox.append(kwargs)
        return True

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.utils.email.send_email", fake_send),
    ):
        result = await reengagement._run(now=now)
    return outbox, result


def _to(outbox, user):
    return [m for m in outbox if m["to"] == user.email]


@pytest.mark.asyncio
async def test_flow_over_a_month_with_at_most_one_email_per_3_days(db_session):
    user = await _user(db_session, last_open_days_ago=0)
    seen: list[tuple[int, str]] = []
    for day in range(0, 45):
        outbox, _ = await _run(NOW + timedelta(days=day))
        seen += [(day, m["subject"]) for m in _to(outbox, user)]
    days = [d for d, _ in seen]
    assert [s for _, s in seen] == [
        "Three picks from your sources",
        "Would a weekly digest suit you better?",
        "We'll stop nudging you",
    ]
    assert days == [3, 10, 30]
    assert all(b - a >= 3 for a, b in pairwise(days))


@pytest.mark.asyncio
async def test_emails_are_gentle_and_unsubscribable(db_session):
    user = await _user(db_session, last_open_days_ago=4)
    outbox, _ = await _run()
    mail = _to(outbox, user)[0]
    assert "<" in mail["extra_headers"]["List-Unsubscribe"]
    assert mail["extra_headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert mail["text_body"] and "Stop digest emails" in mail["text_body"]
    for word in ("miss", "lonely", "sad", "ignored", "piling"):
        assert word not in mail["html_body"].lower()


@pytest.mark.asyncio
async def test_skips_email_off_and_resets_after_an_open(db_session):
    off = await _user(db_session, last_open_days_ago=12, digest_frequency="in_app_only")
    came_back = await _user(
        db_session,
        last_open_days_ago=1,
        reengagement_stage=ASK,
        reengagement_sent_at=NOW - timedelta(days=5),
    )
    came_back_id = came_back.id
    outbox, _ = await _run()
    assert not _to(outbox, off) and not _to(outbox, came_back)
    async with TestingSessionLocal() as s:
        assert (await s.get(User, came_back_id)).reengagement_stage == 0  # opened since: start over


@pytest.mark.asyncio
async def test_switch_to_weekly_link(client, db_session):
    user = await _user(
        db_session,
        last_open_days_ago=11,
        reengagement_stage=LIGHT,
        reengagement_sent_at=NOW - timedelta(days=7),
    )
    user_id = user.id
    outbox, _ = await _run()
    mail = _to(outbox, user)[0]
    import re

    link = (
        re.search(r'href="([^"]*/digest/u/weekly[^"]*)"', mail["html_body"])
        .group(1)
        .replace("&amp;", "&")
    )
    url = urlparse(link)
    params = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert (await client.get(url.path, params=params)).status_code == 200  # inert page
    async with TestingSessionLocal() as s:
        assert (await s.get(User, user_id)).digest_frequency == "daily"
    assert (await client.post(url.path, params=params)).status_code == 303
    async with TestingSessionLocal() as s:
        assert (await s.get(User, user_id)).digest_frequency == "weekly"
    bad = dict(params, sig="0" * 64)
    assert (await client.post(url.path, params=bad)).status_code == 401


@pytest.mark.asyncio
async def test_final_stage_can_also_pause_digest_emails(db_session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "reengagement_pause_digest_at_final", True)
    user = await _user(
        db_session,
        last_open_days_ago=31,
        reengagement_stage=ASK,
        reengagement_sent_at=NOW - timedelta(days=20),
    )
    user_id = user.id
    outbox, _ = await _run()
    assert _to(outbox, user)[0]["subject"] == "We'll stop nudging you"
    async with TestingSessionLocal() as s:
        assert (await s.get(User, user_id)).digest_frequency == "in_app_only"
