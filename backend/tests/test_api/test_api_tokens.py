"""API tokens (EC-03): issue, scopes, revoke, contract shape."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.api_token import ApiToken
from app.models.user import User


@pytest.mark.asyncio
async def test_token_lifecycle_read_scope(client: AsyncClient, test_user_data: dict, db_session):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    jwt = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()

    created = await client.post(
        "/api/v1/tokens", json={"name": "ext", "scopes": ["read"]}, headers=jwt
    )
    assert created.status_code == 201
    body = created.json()
    assert body["token"].startswith("rp_")
    assert body["scopes"] == ["read"]
    tok = {"Authorization": f"Bearer {body['token']}"}

    # Read scope works on GETs.
    feed = await client.get("/api/v1/content/feed", headers=tok)
    assert feed.status_code == 200

    # Read scope is rejected on mutations.
    denied = await client.post(
        "/api/v1/sources", json={"url": "https://x.example/feed"}, headers=tok
    )
    assert denied.status_code == 403
    assert "read-only" in denied.json()["detail"]

    # Only the hash is stored.
    row = (
        await db_session.execute(select(ApiToken).where(ApiToken.user_id == user.id))
    ).scalar_one()
    assert row.token_hash != body["token"]
    assert row.use_count >= 1

    # The list shows the prefix, never the token.
    listed = await client.get("/api/v1/tokens", headers=jwt)
    assert listed.status_code == 200
    entry = listed.json()[0]
    assert entry["prefix"] == body["token"][:12]
    assert "token" not in entry

    # Revocation blocks further use.
    revoked = await client.delete(f"/api/v1/tokens/{body['id']}", headers=jwt)
    assert revoked.status_code == 200
    after = await client.get("/api/v1/content/feed", headers=tok)
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_write_scope_can_mutate(client: AsyncClient, test_user_data: dict):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    jwt = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    created = await client.post(
        "/api/v1/tokens", json={"name": "rw", "scopes": ["read", "write"]}, headers=jwt
    )
    tok = {"Authorization": f"Bearer {created.json()['token']}"}

    listed = await client.get("/api/v1/preferences", headers=tok)
    assert listed.status_code == 200
    updated = await client.put("/api/v1/preferences", json={"timezone": "UTC"}, headers=tok)
    assert updated.status_code == 200


@pytest.mark.asyncio
async def test_openapi_is_published(client: AsyncClient):
    """EC-03 contract: the versioned API exposes its OpenAPI document."""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["version"] == "1.0.0"
    assert "/api/v1/tokens" in spec["paths"]
    assert "/api/v1/content/feed" in spec["paths"]


@pytest.mark.asyncio
async def test_api_token_cannot_mint_or_revoke_tokens(client: AsyncClient, test_user_data: dict):
    """CWE-269 (CodeRabbit): token management is JWT-session-only."""
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    jwt = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    created = await client.post(
        "/api/v1/tokens", json={"name": "rw", "scopes": ["read", "write"]}, headers=jwt
    )
    tok = {"Authorization": f"Bearer {created.json()['token']}"}

    mint = await client.post("/api/v1/tokens", json={"name": "escape"}, headers=tok)
    assert mint.status_code == 403
    assert "session" in mint.json()["detail"]

    revoke = await client.delete(f"/api/v1/tokens/{created.json()['id']}", headers=tok)
    assert revoke.status_code == 403

    # The JWT session still manages tokens normally.
    ok = await client.get("/api/v1/tokens", headers=jwt)
    assert ok.status_code == 200
