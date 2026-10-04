"""Sidecar import (EC-07): Miniflux + FreshRSS against a mock upstream."""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.source import Source
from app.models.user import User
from app.services.integrations import sidecar
from app.services.integrations.sidecar import import_from_freshrss, import_from_miniflux


class _MockTransport(httpx.AsyncBaseTransport):
    """Serves a tiny Miniflux + FreshRSS on https://reader.example."""

    def __init__(self):
        self.miniflux_calls: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/v1/feeds" in path:
            self.miniflux_calls.append(path)
            return httpx.Response(
                200,
                json={
                    "feeds": [
                        {"feed_url": "https://mn1.example/feed", "title": "MN One"},
                        {"feed_url": "https://mn2.example/feed", "title": "MN Two"},
                    ]
                },
            )
        if "/v1/entries" in path:
            self.miniflux_calls.append(path)
            return httpx.Response(
                200,
                json={
                    "entries": [
                        {"url": "https://ingested.example/article"},
                    ]
                },
            )
        if "ClientLogin" in path:
            return httpx.Response(200, text="SID=x\nAuth=freshtoken\n")
        if "subscription/list" in path:
            assert request.headers.get("Authorization") == "GoogleLogin auth=freshtoken"
            return httpx.Response(
                200,
                json={
                    "subscriptions": [
                        {"url": "https://fr1.example/feed", "title": "FR One"},
                        {
                            "url": "https://mn1.example/feed",
                            "title": "MN One",
                        },  # dedup across imports
                    ]
                },
            )
        return httpx.Response(404)


@pytest.fixture
def mock_transport(monkeypatch):
    transport = _MockTransport()
    original = sidecar.safe_fetch

    async def _patched(url: str, **kwargs):
        kwargs.setdefault("transport", transport)
        kwargs.setdefault("resolver", lambda host: ["93.184.216.34"])
        return await original(url, **kwargs)

    monkeypatch.setattr(sidecar, "safe_fetch", _patched)
    return transport


@pytest.mark.asyncio
async def test_miniflux_import_feeds_and_read_state(db_session, mock_transport):
    user = User(email="sc-mn@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    item = ContentItem(
        url="https://ingested.example/article",
        title="Read on Miniflux",
        fetched_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    db_session.add(item)
    await db_session.commit()

    result = await import_from_miniflux(user, "https://reader.example", "tok", db_session)

    assert result.feeds_added == 2
    assert result.feeds_existing == 0
    assert result.read_marked == 1  # matched the already-ingested article

    urls = {
        s.url
        for s in (
            await db_session.execute(select(Source).where(Source.user_id == user.id))
        ).scalars()
    }
    assert urls == {"https://mn1.example/feed", "https://mn2.example/feed"}
    ix = (
        await db_session.execute(
            select(UserContentInteraction).where(
                UserContentInteraction.user_id == user.id,
                UserContentInteraction.content_item_id == item.id,
            )
        )
    ).scalar_one()
    assert ix.opened_at is not None


@pytest.mark.asyncio
async def test_freshrss_import_and_cross_import_dedup(db_session, mock_transport):
    user = User(email="sc-fr@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.commit()

    result = await import_from_freshrss(
        user, "https://reader.example", "me", "app-pass", db_session
    )
    # fr1 is new; mn1 was already imported by the Miniflux test user? No —
    # dedupe is per user; here both are new.
    assert result.feeds_added == 2

    # Re-import: everything already exists.
    again = await import_from_freshrss(user, "https://reader.example", "me", "app-pass", db_session)
    assert again.feeds_added == 0
    assert again.feeds_existing == 2


@pytest.mark.asyncio
async def test_cleartext_sidecar_url_is_rejected(db_session):
    user = User(email="sc-http@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    result = await import_from_miniflux(user, "http://reader.example", "tok", db_session)
    assert result.feeds_added == 0
    assert result.errors
