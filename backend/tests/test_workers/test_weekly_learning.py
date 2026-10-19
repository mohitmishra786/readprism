"""Weekly 'What I learned about you' email (#184)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.interest_graph import InterestNode
from app.models.source import Source
from app.models.user import User
from tests.conftest import TestingSessionLocal

NOW = datetime(2026, 10, 18, 9, tzinfo=UTC)


async def _reader(db_session, *, weekly=True, verified=True):
    user = User(
        email=f"wk{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="x",
        onboarding_complete=True,
        weekly_email=weekly,
        email_verified_at=NOW - timedelta(days=30) if verified else None,
    )
    db_session.add(user)
    await db_session.flush()
    src = Source(user_id=user.id, url="https://wk.example/", name="Loop Unrolled")
    db_session.add(src)
    for label, weight in (("compilers", 0.8), ("databases", 0.75), ("gardening", 0.3)):
        db_session.add(InterestNode(user_id=user.id, topic_label=label, weight=weight))
    await db_session.flush()

    def read(topic, days_ago, **kw):
        item = ContentItem(
            source_id=src.id,
            url=f"https://wk.example/{uuid.uuid4().hex}",
            title=topic,
            topic_clusters=[topic],
        )
        db_session.add(item)
        return item, kw, NOW - timedelta(days=days_ago)

    reads = [
        read("compilers", 1, read_completion_pct=0.95),
        read("compilers", 2, saved=True, read_completion_pct=0.9),
        read("compilers", 3, explicit_rating=1),
        read("compilers", 9, read_completion_pct=0.9),
        read("databases", 10, read_completion_pct=0.95),
        read("databases", 11, read_completion_pct=0.95),
    ]
    await db_session.flush()
    for item, kw, when in reads:
        db_session.add(
            UserContentInteraction(
                user_id=user.id, content_item_id=item.id, created_at=when, opened_at=when, **kw
            )
        )
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_rising_fading_and_top_source(db_session):
    from app.services.digest.weekly_learning import compute

    user = await _reader(db_session)
    learning = await compute(user, db_session, NOW)
    assert learning.rising[0][0] == "compilers"  # 5 engagement points this week vs 1
    assert learning.fading == "databases"  # strong interest, nothing this week
    assert learning.top_source == ("Loop Unrolled", 2)


async def _run(outbox):
    from unittest.mock import patch

    from app.workers.tasks.weekly_learning import _run

    async def fake_send(**kwargs):
        outbox.append(kwargs)
        return True

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.utils.email.send_email", fake_send),
    ):
        return await _run(now=NOW)


@pytest.mark.asyncio
async def test_sent_weekly_to_opted_in_verified_users_only(db_session):
    on = await _reader(db_session)
    off = await _reader(db_session, weekly=False)
    unverified = await _reader(db_session, verified=False)
    outbox: list[dict] = []
    await _run(outbox)
    recipients = {m["to"] for m in outbox}
    assert on.email in recipients and off.email not in recipients
    from app.services.email_verification import may_email

    assert (unverified.email in recipients) == may_email(unverified)
    mail = next(m for m in outbox if m["to"] == on.email)
    assert (
        mail["extra_headers"]["List-Unsubscribe"].startswith("<")
        and "unsubscribe-weekly" in mail["extra_headers"]["List-Unsubscribe"]
    )
    assert "Rising:" in mail["text_body"] and "compilers" in mail["text_body"]  # plain-text version
    assert "Less like this" in mail["html_body"] and "keep it" in mail["html_body"]

    # Idempotent within the week.
    again: list[dict] = []
    await _run(again)
    assert on.email not in {m["to"] for m in again}


@pytest.mark.asyncio
async def test_nothing_to_report_sends_nothing(db_session):
    user = User(
        email=f"q{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="x",
        weekly_email=True,
        email_verified_at=NOW,
    )
    db_session.add(user)
    await db_session.commit()
    outbox: list[dict] = []
    await _run(outbox)
    assert user.email not in {m["to"] for m in outbox}


@pytest.mark.asyncio
async def test_undo_links_adjust_the_graph_only_on_post(client, db_session):
    from app.utils.signed_links import topic_action_url

    user = await _reader(db_session)
    user_id = user.id
    url = urlparse(topic_action_url(user_id, "compilers", "less"))
    path = url.path
    query = {k: v[0] for k, v in parse_qs(url.query).items()}

    async def weight():
        db_session.expire_all()
        return (
            await db_session.execute(
                select(InterestNode.weight).where(
                    InterestNode.user_id == user_id, InterestNode.topic_label == "compilers"
                )
            )
        ).scalar_one()

    page = await client.get(path, params=query)
    assert page.status_code == 200 and "compilers" in page.text and 'method="post"' in page.text
    assert await weight() == pytest.approx(0.8)  # a mail scanner's GET changes nothing
    done = await client.post(path, params=query)
    assert done.status_code == 303 and done.headers["location"].endswith("/interests")
    assert await weight() == pytest.approx(0.5)

    bad = dict(query, sig="0" * 64)
    assert (await client.post(path, params=bad)).status_code == 401
    other_topic = dict(query, topic="databases")  # signature is bound to the topic
    assert (await client.post(path, params=other_topic)).status_code == 401


@pytest.mark.asyncio
async def test_weekly_unsubscribe_turns_off_only_the_weekly_email(client, db_session):
    from app.utils.unsubscribe import weekly_unsubscribe_url

    user = await _reader(db_session)
    user_id, frequency = user.id, user.digest_frequency
    url = urlparse(weekly_unsubscribe_url(user_id))
    resp = await client.post(url.path, params={k: v[0] for k, v in parse_qs(url.query).items()})
    assert resp.status_code == 200
    db_session.expire_all()
    refreshed = await db_session.get(User, user_id)
    assert refreshed.weekly_email is False and refreshed.digest_frequency == frequency


@pytest.mark.asyncio
async def test_preference_toggle(client, test_user_data):
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    assert (await client.get("/api/v1/preferences", headers=headers)).json()[
        "weekly_email"
    ] is False
    resp = await client.put("/api/v1/preferences", json={"weekly_email": True}, headers=headers)
    assert resp.json()["weekly_email"] is True


def test_weekly_beat_entry_is_routed():
    from app.workers.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["weekly-learning-emails"]
    assert entry["task"] == "app.workers.tasks.weekly_learning.send_weekly_learning_emails"
    assert celery_app.conf.task_routes["app.workers.tasks.weekly_learning.*"] == {"queue": "digest"}
