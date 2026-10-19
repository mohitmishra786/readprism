"""Never an empty digest on a quiet day (#142)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import Digest, DigestItem
from app.models.source import Source
from app.models.user import User
from app.services.digest.builder import QUIET_FALLBACK_LABEL, build_digest


async def _reader(db_session):
    user = User(
        email=f"q{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", digest_max_items=6
    )
    db_session.add(user)
    await db_session.flush()
    src = Source(user_id=user.id, url="https://quiet.example", feed_url="https://quiet.example/f")
    db_session.add(src)
    await db_session.flush()
    return user, src


def _item(src, i, *, age):
    return ContentItem(
        source_id=src.id,
        url=f"https://quiet.example/{uuid.uuid4().hex[:6]}-{i}",
        title=f"Older post {i}",
        topic_clusters=[f"t{i}"],
        summary_brief="ok",
        fetched_at=datetime.now(UTC) - age,
    )


async def _items_of(db_session, digest):
    return (
        await db_session.execute(
            select(DigestItem, ContentItem)
            .join(ContentItem, ContentItem.id == DigestItem.content_item_id)
            .where(DigestItem.digest_id == digest.id)
        )
    ).all()


@pytest.mark.asyncio
async def test_zero_new_items_gives_labelled_catch_up_items(db_session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "digest_per_source_cap", 50)
    user, src = await _reader(db_session)
    fresh_enough = [_item(src, i, age=timedelta(days=3 + i)) for i in range(4)]
    too_old = _item(src, 99, age=timedelta(days=30))
    already_read = _item(src, 98, age=timedelta(days=2))
    db_session.add_all([*fresh_enough, too_old, already_read])
    await db_session.flush()
    db_session.add(
        UserContentInteraction(
            user_id=user.id, content_item_id=already_read.id, opened_at=datetime.now(UTC)
        )
    )
    await db_session.commit()

    digest = await build_digest(user, db_session)
    await db_session.commit()

    rows = await _items_of(db_session, digest)
    own = {c.id for _, c in rows if c.source_id == src.id}
    assert own == {i.id for i in fresh_enough}
    for di, c in rows:
        if c.id in own:
            assert di.signal_breakdown["fallback_reason"] == QUIET_FALLBACK_LABEL

    # Items already shown in a digest don't come back on the next quiet day.
    again = await build_digest(user, db_session)
    await db_session.commit()
    assert not {c.id for _, c in await _items_of(db_session, again)} & own


@pytest.mark.asyncio
async def test_no_fallback_when_there_is_new_content(db_session):
    user, src = await _reader(db_session)
    db_session.add_all(
        [_item(src, 0, age=timedelta(hours=2)), _item(src, 1, age=timedelta(days=4))]
    )
    await db_session.commit()

    digest = await build_digest(user, db_session)
    await db_session.commit()

    rows = await _items_of(db_session, digest)
    assert rows and all("fallback_reason" not in di.signal_breakdown for di, _ in rows)
    assert (
        (await db_session.execute(select(Digest).where(Digest.user_id == user.id)))
        .scalars()
        .first()
    )
