from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_creates_user(client: AsyncClient, test_user_data: dict):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_returns_token(client: AsyncClient, test_user_data: dict):
    await client.post("/api/v1/auth/register", json=test_user_data)
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user_data["email"],
            "password": test_user_data["password"],
        },
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_profile(client: AsyncClient, test_user_data: dict):
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    token = reg.json()["access_token"]
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == test_user_data["email"]


@pytest.mark.asyncio
async def test_login_returns_refresh_token(client: AsyncClient, test_user_data: dict):
    await client.post("/api/v1/auth/register", json=test_user_data)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user_data["email"], "password": test_user_data["password"]},
    )
    body = resp.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] == 1800


@pytest.mark.asyncio
async def test_refresh_rotates_and_revokes_old(client: AsyncClient, test_user_data: dict):
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    refresh_token = reg.json()["refresh_token"]

    # First rotation succeeds and returns a new pair.
    r1 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r1.status_code == 200
    new_refresh = r1.json()["refresh_token"]
    assert new_refresh != refresh_token

    # Reusing the old (rotated-out) refresh token is rejected.
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r2.status_code == 401

    # The new refresh token still works.
    r3 = await client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert r3.status_code == 200


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client: AsyncClient, test_user_data: dict):
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    refresh_token = reg.json()["refresh_token"]
    out = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert out.status_code == 204
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_rejected_as_access(client: AsyncClient, test_user_data: dict):
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    refresh_token = reg.json()["refresh_token"]
    # A refresh token must not authenticate protected endpoints.
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_magic_link_request_and_verify(client: AsyncClient, monkeypatch):
    """Request emails a link (non-enumerating 202) and the token signs you in once."""
    from app.api import auth as auth_mod

    sent = {}

    async def fake_send(**kwargs):
        sent["to"] = kwargs["to"]
        sent["html"] = kwargs["html_body"]
        return True

    monkeypatch.setattr("app.utils.email.send_email", fake_send)

    import uuid as _uuid

    email = f"magic_{_uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post("/api/v1/auth/magic-link/request", json={"email": email})
    assert resp.status_code == 202
    assert sent["to"] == email

    # Extract the token from the emailed link.
    token = sent["html"].split("token=")[1].split('"')[0]
    v = await client.post("/api/v1/auth/magic-link/verify", json={"token": token})
    assert v.status_code == 200
    assert v.json()["access_token"] and v.json()["refresh_token"]

    # Single-use: replay is rejected.
    replay = await client.post("/api/v1/auth/magic-link/verify", json={"token": token})
    assert replay.status_code == 401


@pytest.mark.asyncio
async def test_magic_link_verify_rejects_garbage(client: AsyncClient):
    resp = await client.post("/api/v1/auth/magic-link/verify", json={"token": "not-a-token"})
    assert resp.status_code == 401
