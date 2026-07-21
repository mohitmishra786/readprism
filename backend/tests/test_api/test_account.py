"""Tests for GDPR account export + erasure endpoints (audit 06-3)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.interest_graph import InterestNode
from app.models.source import Source
from app.models.user import User


async def _register(client: AsyncClient, data: dict) -> str:
    resp = await client.post("/api/v1/auth/register", json=data)
    assert resp.status_code == 201
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_export_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/account/export")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_export_returns_user_bundle(client: AsyncClient, test_user_data: dict, db_session):
    token = await _register(client, test_user_data)
    # Seed a source + interest node directly so the export has content.
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    db_session.add(Source(user_id=user.id, url="https://example.com/feed", source_type="rss"))
    db_session.add(InterestNode(user_id=user.id, topic_label="compilers", weight=0.7))
    await db_session.commit()

    resp = await client.get("/api/v1/account/export", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("attachment")
    bundle = resp.json()
    assert bundle["profile"]["email"] == test_user_data["email"]
    assert "hashed_password" not in bundle["profile"]  # secret excluded
    assert any(s["url"] == "https://example.com/feed" for s in bundle["sources"])
    assert any(n["topic_label"] == "compilers" for n in bundle["interest_nodes"])
    assert {
        "profile",
        "sources",
        "creators",
        "interactions",
        "interest_nodes",
        "meta_weights",
    }.issubset(bundle.keys())


@pytest.mark.asyncio
async def test_delete_account_removes_user_and_cascades(
    client: AsyncClient, test_user_data: dict, db_session
):
    token = await _register(client, test_user_data)
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    uid = user.id
    db_session.add(Source(user_id=uid, url="https://example.com/feed", source_type="rss"))
    db_session.add(InterestNode(user_id=uid, topic_label="rust", weight=0.6))
    await db_session.commit()

    resp = await client.delete("/api/v1/account", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 204

    # User row and cascaded rows are gone.
    assert (
        await db_session.execute(select(User).where(User.id == uid))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(Source).where(Source.user_id == uid))
    ).scalars().all() == []
    assert (
        await db_session.execute(select(InterestNode).where(InterestNode.user_id == uid))
    ).scalars().all() == []

    # Token no longer works.
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 401
