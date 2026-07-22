"""Auth rate-limiting + non-enumerating login (audit 06-4)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.utils import ratelimit


@pytest.mark.asyncio
async def test_login_does_not_enumerate_accounts(client: AsyncClient, test_user_data: dict):
    """A wrong password and a non-existent account return the identical 401."""
    await client.post("/api/v1/auth/register", json=test_user_data)

    wrong_pw = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user_data["email"], "password": "definitely-wrong"},
    )
    no_account = await client.post(
        "/api/v1/auth/login",
        json={"email": f"ghost_{uuid.uuid4().hex}@example.com", "password": "whatever"},
    )
    assert wrong_pw.status_code == no_account.status_code == 401
    assert wrong_pw.json()["detail"] == no_account.json()["detail"]


@pytest.mark.asyncio
async def test_register_is_rate_limited(client: AsyncClient, monkeypatch):
    """With a low register limit, the N+1th attempt from one IP is 429."""
    from app.api import auth
    from app.main import app

    # Re-enable limiting (autouse fixture disabled it) with a tiny window/limit,
    # substituting our limiter for the route's original dependency instance.
    limiter = ratelimit.RateLimiter(
        max_requests=3, window_seconds=60, scope=f"reg-{uuid.uuid4().hex}"
    )
    monkeypatch.setattr(ratelimit.settings, "rate_limit_enabled", True)
    app.dependency_overrides[auth.register_rate_limit] = limiter
    try:
        statuses = []
        for _ in range(5):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"u_{uuid.uuid4().hex}@example.com",
                    "password": "TestPass123!",
                    "display_name": "U",
                },
            )
            statuses.append(resp.status_code)
    finally:
        app.dependency_overrides.pop(auth.register_rate_limit, None)

    assert 429 in statuses, statuses
    assert statuses[:3] == [201, 201, 201]
