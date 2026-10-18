"""Plan entitlements by deployment mode (#109, audit 13-1/13-5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.digest import Digest
from app.models.source import Source
from app.models.user import User
from app.services import entitlements


async def _register(client: AsyncClient, data: dict, db_session) -> tuple[dict, User]:
    reg = await client.post("/api/v1/auth/register", json=data)
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    user = (await db_session.execute(select(User).where(User.email == data["email"]))).scalar_one()
    return headers, user


async def _seed_sources(db_session, user: User, n: int) -> None:
    db_session.add_all(Source(user_id=user.id, url=f"https://s{i}.example.com") for i in range(n))
    await db_session.commit()


async def _add_source(client: AsyncClient, headers: dict, url: str):
    with (
        patch("app.api.sources._autodiscover_feed", new=AsyncMock(return_value=None)),
        patch("app.workers.tasks.ingest_feeds.ingest_user_sources.delay"),
    ):
        return await client.post("/api/v1/sources", json={"url": url}, headers=headers)


def _opml(n: int) -> bytes:
    outlines = "".join(
        f'<outline type="rss" text="F{i}" xmlUrl="https://feed{i}.example.com/rss"/>'
        for i in range(n)
    )
    return f'<?xml version="1.0"?><opml version="2.0"><body>{outlines}</body></opml>'.encode()


@pytest.fixture
def hosted(monkeypatch):
    monkeypatch.setattr(entitlements.settings, "deployment_mode", "hosted")


@pytest.mark.asyncio
async def test_selfhost_never_limits_sources(client, test_user_data, db_session, monkeypatch):
    monkeypatch.setattr(entitlements.settings, "free_max_sources", 2)
    headers, user = await _register(client, test_user_data, db_session)
    await _seed_sources(db_session, user, 200)

    resp = await _add_source(client, headers, "https://one-more.example.com")
    assert resp.status_code == 201

    opml = await client.post(
        "/api/v1/sources/import-opml-v2",
        files={"file": ("feeds.opml", _opml(50), "text/xml")},
        headers=headers,
    )
    assert opml.status_code == 200
    total = (
        await db_session.execute(
            select(func.count()).select_from(Source).where(Source.user_id == user.id)
        )
    ).scalar()
    assert total == 251


@pytest.mark.asyncio
async def test_selfhost_digest_regeneration_is_only_a_double_click_guard(
    client, test_user_data, db_session
):
    headers, user = await _register(client, test_user_data, db_session)
    db_session.add(Digest(user_id=user.id, generated_at=datetime.now(UTC) - timedelta(minutes=2)))
    await db_session.commit()

    with patch("app.workers.tasks.build_digest.build_digest_for_user.delay"):
        ok = await client.post("/api/v1/digest/generate", headers=headers)
    assert ok.status_code == 200

    db_session.add(Digest(user_id=user.id, generated_at=datetime.now(UTC)))
    await db_session.commit()
    with patch("app.workers.tasks.build_digest.build_digest_for_user.delay"):
        again = await client.post("/api/v1/digest/generate", headers=headers)
    assert again.status_code == 429
    assert "plan" not in again.json()["detail"].lower()
    assert "upgrade" not in again.json()["detail"].lower()


@pytest.mark.asyncio
async def test_hosted_free_user_blocked_at_source_limit(
    client, test_user_data, db_session, monkeypatch, hosted
):
    monkeypatch.setattr(entitlements.settings, "free_max_sources", 2)
    headers, user = await _register(client, test_user_data, db_session)
    await _seed_sources(db_session, user, 2)

    resp = await _add_source(client, headers, "https://c.example.com")
    assert resp.status_code == 402
    assert "Upgrade" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_hosted_free_user_opml_import_counts_against_the_limit(
    client, test_user_data, db_session, monkeypatch, hosted
):
    monkeypatch.setattr(entitlements.settings, "free_max_sources", 10)
    headers, user = await _register(client, test_user_data, db_session)
    await _seed_sources(db_session, user, 5)

    resp = await client.post(
        "/api/v1/sources/import-opml-v2",
        files={"file": ("feeds.opml", _opml(6), "text/xml")},
        headers=headers,
    )
    assert resp.status_code == 402
    assert "add 5 more" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_hosted_free_user_starter_pack_counts_against_the_limit(
    client, test_user_data, db_session, monkeypatch, hosted
):
    from app.services.cold_start.starter_packs import list_starter_packs

    pack = list_starter_packs()[0]
    monkeypatch.setattr(entitlements.settings, "free_max_sources", len(pack.feeds) - 1)
    headers, _ = await _register(client, test_user_data, db_session)

    resp = await client.post(f"/api/v1/sources/starter-packs/{pack.id}/subscribe", headers=headers)
    assert resp.status_code == 402


@pytest.mark.asyncio
async def test_hosted_free_digest_throttle_uses_plan_window(
    client, test_user_data, db_session, hosted
):
    headers, user = await _register(client, test_user_data, db_session)
    db_session.add(Digest(user_id=user.id, generated_at=datetime.now(UTC) - timedelta(minutes=10)))
    await db_session.commit()

    with patch("app.workers.tasks.build_digest.build_digest_for_user.delay"):
        resp = await client.post("/api/v1/digest/generate", headers=headers)
    assert resp.status_code == 429
    assert "plan" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_hosted_pro_user_unlimited_sources(
    client, test_user_data, db_session, monkeypatch, hosted
):
    monkeypatch.setattr(entitlements.settings, "free_max_sources", 1)
    headers, user = await _register(client, test_user_data, db_session)
    user.tier = "pro"
    await _seed_sources(db_session, user, 1)

    resp = await _add_source(client, headers, "https://c.example.com")
    assert resp.status_code == 201


def test_deployment_mode_is_validated(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("DEPLOYMENT_MODE", "Hosted ")
    assert Settings(_env_file=None).deployment_mode == "hosted"
    monkeypatch.setenv("DEPLOYMENT_MODE", "cloud")
    with pytest.raises(ValueError, match="DEPLOYMENT_MODE"):
        Settings(_env_file=None)
