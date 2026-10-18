"""Browser sessions in httpOnly cookies with CSRF protection (#103)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

COOKIE_MODE = {"X-Auth-Mode": "cookie"}


def _creds() -> dict:
    return {"email": f"c{uuid.uuid4().hex[:8]}@example.com", "password": "TestPass123!"}


def _set_cookie_headers(resp) -> list[str]:
    return resp.headers.get_list("set-cookie")


@pytest.mark.asyncio
async def test_cookie_login_sets_httponly_cookies_and_omits_tokens(client: AsyncClient):
    creds = _creds()
    reg = await client.post("/api/v1/auth/register", json=creds, headers=COOKIE_MODE)

    assert reg.status_code == 201
    body = reg.json()
    assert body["access_token"] == "" and body["refresh_token"] is None
    assert body["csrf_token"]
    cookies = {c.split("=", 1)[0]: c.lower() for c in _set_cookie_headers(reg)}
    for name in ("rp_access", "rp_refresh", "rp_csrf"):
        assert name in cookies, cookies
        assert "httponly" in cookies[name]
        assert "samesite=strict" in cookies[name]
    assert "path=/api/v1/auth" in cookies["rp_refresh"]


@pytest.mark.asyncio
async def test_cookie_session_reads_and_requires_csrf_for_writes(client: AsyncClient):
    reg = await client.post("/api/v1/auth/register", json=_creds(), headers=COOKIE_MODE)
    csrf = reg.json()["csrf_token"]

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200

    no_csrf = await client.put("/api/v1/preferences", json={"digest_max_items": 10})
    assert no_csrf.status_code == 403
    wrong = await client.put(
        "/api/v1/preferences", json={"digest_max_items": 10}, headers={"X-CSRF-Token": "nope"}
    )
    assert wrong.status_code == 403
    ok = await client.put(
        "/api/v1/preferences", json={"digest_max_items": 10}, headers={"X-CSRF-Token": csrf}
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_session_endpoint_restores_csrf_after_reload(client: AsyncClient):
    reg = await client.post("/api/v1/auth/register", json=_creds(), headers=COOKIE_MODE)
    state = (await client.get("/api/v1/auth/session")).json()
    assert state == {
        "authenticated": True,
        "refreshable": True,
        "csrf_token": reg.json()["csrf_token"],
    }


@pytest.mark.asyncio
async def test_cookie_refresh_rotates_and_logout_clears(client: AsyncClient):
    await client.post("/api/v1/auth/register", json=_creds(), headers=COOKIE_MODE)
    old_refresh = client.cookies.get("rp_refresh")

    rotated = await client.post("/api/v1/auth/refresh", headers=COOKIE_MODE)
    assert rotated.status_code == 200
    assert rotated.json()["access_token"] == "" and rotated.json()["csrf_token"]
    assert client.cookies.get("rp_refresh") != old_refresh

    # The rotated-out refresh token is dead.
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh}, headers=COOKIE_MODE
    )
    assert replay.status_code == 401

    out = await client.post("/api/v1/auth/logout")
    assert out.status_code == 204
    client.cookies.clear()  # httpx keeps expired cookies until cleared
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    state = (await client.get("/api/v1/auth/session")).json()
    assert state["authenticated"] is False and state["csrf_token"] is None


@pytest.mark.asyncio
async def test_logout_clears_cookies_in_response(client: AsyncClient):
    await client.post("/api/v1/auth/register", json=_creds(), headers=COOKIE_MODE)
    out = await client.post("/api/v1/auth/logout")
    cleared = " ".join(_set_cookie_headers(out)).lower()
    for name in ("rp_access", "rp_refresh", "rp_csrf"):
        assert f"{name}=" in cleared
    assert "max-age=0" in cleared


@pytest.mark.asyncio
async def test_bearer_clients_are_unchanged(client: AsyncClient):
    reg = await client.post("/api/v1/auth/register", json=_creds())
    body = reg.json()
    assert body["access_token"] and body["refresh_token"]
    assert not _set_cookie_headers(reg)
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    # Bearer auth is not cookie-borne, so no CSRF token is needed.
    ok = await client.put("/api/v1/preferences", json={"digest_max_items": 9}, headers=headers)
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_unauthenticated_request_is_401(client: AsyncClient):
    client.cookies.clear()
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
