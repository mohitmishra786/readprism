"""Preferences API: digest length lock semantics (UX-02)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _auth_header(client: AsyncClient, data: dict) -> dict:
    resp = await client.post("/api/v1/auth/register", json=data)
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_setting_length_explicitly_locks_it(client: AsyncClient, test_user_data: dict):
    headers = await _auth_header(client, test_user_data)

    resp = await client.put("/api/v1/preferences", json={"digest_max_items": 9}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["digest_max_items"] == 9
    assert body["digest_length_locked"] is True


@pytest.mark.asyncio
async def test_auto_flag_unlocks_length(client: AsyncClient, test_user_data: dict):
    headers = await _auth_header(client, test_user_data)

    resp = await client.put("/api/v1/preferences", json={"digest_max_items": 9}, headers=headers)
    assert resp.json()["digest_length_locked"] is True

    resp = await client.put(
        "/api/v1/preferences", json={"digest_length_auto": True}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["digest_length_locked"] is False
    # The explicit value stays until the learner moves it.
    assert resp.json()["digest_max_items"] == 9


@pytest.mark.asyncio
async def test_default_is_unlocked(client: AsyncClient, test_user_data: dict):
    headers = await _auth_header(client, test_user_data)
    resp = await client.get("/api/v1/preferences", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["digest_length_locked"] is False
