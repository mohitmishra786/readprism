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
    resp = await client.post("/api/v1/auth/login", json={
        "email": test_user_data["email"],
        "password": test_user_data["password"],
    })
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
