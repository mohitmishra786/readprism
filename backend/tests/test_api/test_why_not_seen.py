"""'Why didn't I see this?' (#267)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.digest import Digest, DigestItem
from app.models.interest_graph import InterestNode
from app.models.source import Source
from app.models.user import User
from app.services.ranking.ranker import rank


async def _setup(client, db_session):
    email = f"why{uuid.uuid4().hex[:6]}@example.com"
    reg = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "TestPass123!"}
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    src = Source(user_id=user.id, url=f"https://why{uuid.uuid4().hex[:4]}.example/f")
    db_session.add(src)
    db_session.add(InterestNode(user_id=user.id, topic_label="compilers", weight=0.8))
    await db_session.flush()
    return headers, user, src


def _item(src=None, **kw):
    base = {
        "url": f"https://why.example/{uuid.uuid4().hex}",
        "title": "How compilers lower loops",
        "topic_clusters": ["compilers"],
        "fetched_at": datetime.now(UTC) - timedelta(hours=2),
        "word_count": 1200,
    }
    return ContentItem(source_id=src.id if src else None, **{**base, **kw})


@pytest.mark.asyncio
async def test_explanation_is_the_live_rankers_own(client, db_session):
    headers, user, src = await _setup(client, db_session)
    item = _item(src)
    db_session.add(item)
    await db_session.commit()
    item_id, user_id = item.id, user.id

    body = (await client.get(f"/api/v1/search/why/{item_id}", headers=headers)).json()

    db_session.expire_all()
    expected = (
        await rank(
            await db_session.get(User, user_id),
            [await db_session.get(ContentItem, item_id)],
            db_session,
        )
    )[0]
    assert body["score"] == pytest.approx(expected.prs, abs=1e-4)
    assert body["explanation"] == expected.explanation  # the digest's wording
    total = sum(row["contribution"] for row in body["contributions"])
    assert total == pytest.approx(body["score"], abs=1e-3)
    assert [r["contribution"] for r in body["contributions"]] == sorted(
        (r["contribution"] for r in body["contributions"]), reverse=True
    )
    assert body["verdict"] == "no_digest_yet"
    assert 1 <= len(body["raise_it"]) <= 2


@pytest.mark.asyncio
async def test_verdicts(client, db_session):
    headers, user, src = await _setup(client, db_session)
    shown, low, listing = _item(src), _item(src, title="Unrelated note"), _item(src, rankable=False)
    elsewhere = _item(None)
    db_session.add_all([shown, low, listing, elsewhere])
    await db_session.flush()
    digest = Digest(user_id=user.id, total_items=1, generated_at=datetime(2026, 10, 19, tzinfo=UTC))
    db_session.add(digest)
    await db_session.flush()
    db_session.add(
        DigestItem(
            digest_id=digest.id,
            content_item_id=shown.id,
            position=2,
            section="lead",
            prs_score=0.99,
            signal_breakdown={},
        )
    )
    await db_session.commit()

    async def verdict(item):
        return (await client.get(f"/api/v1/search/why/{item.id}", headers=headers)).json()

    got = await verdict(shown)
    assert got["verdict"] == "shown" and "October 19, at position 3" in got["message"]
    got = await verdict(low)
    assert got["verdict"] == "ranked_below_cutoff" and got["latest_digest_cutoff"] == 0.99
    assert (await verdict(listing))["verdict"] == "not_an_article"
    assert (await verdict(elsewhere))["verdict"] == "not_followed"


@pytest.mark.asyncio
async def test_unknown_item_is_not_found(client, db_session):
    headers, _, _ = await _setup(client, db_session)
    resp = await client.get(f"/api/v1/search/why/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404
