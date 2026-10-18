"""Private saves are per user and invisible to others (#101)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.services.content_lookup import find_visible_item

URL = "https://shared-interest.example/article"


async def _write_token(client: AsyncClient) -> tuple[dict, str]:
    data = {"email": f"u{uuid.uuid4().hex[:8]}@example.com", "password": "TestPass123!"}
    reg = await client.post("/api/v1/auth/register", json=data)
    jwt = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    created = await client.post(
        "/api/v1/tokens", json={"name": "ext", "scopes": ["read", "write"]}, headers=jwt
    )
    return {"Authorization": f"Bearer {created.json()['token']}"}, data["email"]


async def _user(db_session, email: str) -> User:
    return (await db_session.execute(select(User).where(User.email == email))).scalar_one()


@pytest.mark.asyncio
async def test_two_users_can_save_the_same_url_privately(client: AsyncClient, db_session):
    tok_a, email_a = await _write_token(client)
    tok_b, email_b = await _write_token(client)

    res_a = await client.post(
        "/api/v1/extension/save", json={"url": URL, "title": "A"}, headers=tok_a
    )
    res_b = await client.post(
        "/api/v1/extension/save", json={"url": URL, "title": "B"}, headers=tok_b
    )

    assert res_a.status_code == 201 and res_b.status_code == 201
    assert "another user" not in res_b.text
    assert res_a.json()["content_item_id"] != res_b.json()["content_item_id"]
    rows = list(
        (await db_session.execute(select(ContentItem).where(ContentItem.url == URL))).scalars()
    )
    owners = {row.owner_user_id for row in rows}
    assert owners == {(await _user(db_session, email_a)).id, (await _user(db_session, email_b)).id}


@pytest.mark.asyncio
async def test_save_reuses_the_public_row_when_one_exists(client: AsyncClient, db_session):
    public = ContentItem(url=URL, title="From a feed")
    db_session.add(public)
    await db_session.commit()
    tok, email = await _write_token(client)

    res = await client.post(
        "/api/v1/extension/save", json={"url": URL, "title": "X", "rating": 1}, headers=tok
    )

    assert res.json()["content_item_id"] == str(public.id)
    user = await _user(db_session, email)
    ix = (
        await db_session.execute(
            select(UserContentInteraction).where(UserContentInteraction.user_id == user.id)
        )
    ).scalar_one()
    assert ix.content_item_id == public.id and ix.saved and ix.explicit_rating == 1


@pytest.mark.asyncio
async def test_public_row_can_be_created_after_private_saves(db_session):
    owner = User(email="owner@example.com", hashed_password="x")
    db_session.add(owner)
    await db_session.flush()
    db_session.add(
        ContentItem(url=URL, title="Private", owner_user_id=owner.id, origin="extension")
    )
    await db_session.flush()

    db_session.add(ContentItem(url=URL, title="Public from feed"))
    await db_session.flush()  # previously: IntegrityError on the global unique URL

    # A second public row for the same URL is still rejected.
    db_session.add(ContentItem(url=URL, title="Duplicate public"))
    with pytest.raises(Exception, match="uq_content_items_public_url"):
        await db_session.flush()


@pytest.mark.asyncio
async def test_saved_import_is_not_blocked_by_another_users_private_row(
    client: AsyncClient, db_session
):
    other = User(email="other-importer@example.com", hashed_password="x")
    db_session.add(other)
    await db_session.flush()
    db_session.add(ContentItem(url=URL, title="Theirs", owner_user_id=other.id, origin="import"))
    await db_session.commit()

    tok, email = await _write_token(client)
    csv_text = f"URL,Title,Selection\n{URL},Mine,\n"
    res = await client.post(
        "/api/v1/sources/import-saved?kind=instapaper",
        files={"file": ("instapaper.csv", csv_text.encode(), "text/csv")},
        headers=tok,
    )

    assert res.status_code == 200 and res.json()["created"] == 1
    user = await _user(db_session, email)
    mine = await find_visible_item(db_session, user.id, URL)
    assert mine is not None and mine.owner_user_id == user.id


@pytest.mark.asyncio
async def test_other_users_private_rows_are_invisible(db_session):
    a = User(email="vis-a@example.com", hashed_password="x")
    b = User(email="vis-b@example.com", hashed_password="x")
    db_session.add_all([a, b])
    await db_session.flush()
    db_session.add(ContentItem(url=URL, title="A's", owner_user_id=a.id))
    await db_session.flush()

    assert await find_visible_item(db_session, b.id, URL) is None
    assert (await find_visible_item(db_session, a.id, URL)).owner_user_id == a.id

    public = ContentItem(url=URL, title="Public")
    db_session.add(public)
    await db_session.flush()
    assert (await find_visible_item(db_session, a.id, URL)).id == public.id
