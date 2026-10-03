"""Markdown exports (EC-05): Logseq golden files, zip, webhook delivery."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.user import User
from app.services.integrations.export import _to_logseq, export_to_logseq


def _saved_item() -> ContentItem:
    return ContentItem(
        url="https://golden.example/postgres",
        title="Postgres Full-Text Search",
        author="Ada",
        topic_clusters=["databases", "postgres"],
        summary_brief="How tsvector works.",
        full_text="Intro paragraph.\n\nSecond paragraph.",
        fetched_at=datetime(2026, 10, 1, tzinfo=UTC),
    )


def _interaction() -> UserContentInteraction:
    return UserContentInteraction(
        user_id=None,
        content_item_id=None,
        saved=True,
        saved_read_at=datetime(2026, 10, 2, tzinfo=UTC),
    )


def test_logseq_golden_file():
    filename, body = _to_logseq(_saved_item(), _interaction())
    assert filename == "readprism/Postgres-Full-Text-Search.md"
    assert body.startswith("- ## Postgres Full-Text Search")
    assert "source:: https://golden.example/postgres" in body
    assert "author:: Ada" in body
    assert "type:: readprism" in body
    assert "[[databases]] [[postgres]]" in body
    assert "- > How tsvector works." in body
    assert "- Intro paragraph." in body and "- Second paragraph." in body
    assert "original:: [https://golden.example/postgres]" in body


@pytest.mark.asyncio
async def test_export_zip_and_logseq_endpoint(
    client: AsyncClient, test_user_data: dict, db_session
):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()

    item = _saved_item()
    db_session.add(item)
    await db_session.flush()
    db_session.add(UserContentInteraction(user_id=user.id, content_item_id=item.id, saved=True))
    await db_session.commit()

    listed = await client.get("/api/v1/integrations/logseq", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    zip_resp = await client.get("/api/v1/integrations/export-zip?format=logseq", headers=headers)
    assert zip_resp.status_code == 200
    assert zip_resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
        names = zf.namelist()
        assert names == ["readprism/Postgres-Full-Text-Search.md"]
        assert b"- ## Postgres Full-Text Search" in zf.read(names[0])


@pytest.mark.asyncio
async def test_webhook_export_uses_safe_fetch(
    client: AsyncClient, test_user_data: dict, db_session
):
    from unittest.mock import patch

    from app.utils import ssrf

    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    item = _saved_item()
    db_session.add(item)
    await db_session.flush()
    db_session.add(UserContentInteraction(user_id=user.id, content_item_id=item.id, saved=True))
    await db_session.commit()

    delivered: list[bytes] = []

    class _Resp:
        status_code = 200

    async def _fake_safe_fetch(url, **kwargs):
        delivered.append(kwargs.get("content") or b"")
        return _Resp()

    # A private target must be rejected by the REAL guard before delivery.
    with patch.object(ssrf, "safe_fetch", _fake_safe_fetch):
        result = await client.post(
            "/api/v1/integrations/export-webhook",
            json={"url": "https://hook.example/receive", "format": "logseq"},
            headers=headers,
        )
    assert result.status_code == 200
    assert result.json()["delivered"] == 1
    payload = json.loads(delivered[0])
    assert payload["filename"].startswith("readprism/")

    # The real guard blocks loopback targets outright.
    blocked = await client.post(
        "/api/v1/integrations/export-webhook",
        json={"url": "http://127.0.0.1:9/nowhere", "format": "logseq"},
        headers=headers,
    )
    assert blocked.status_code == 200  # handled per-file
    assert blocked.json()["delivered"] == 0
    assert blocked.json()["errors"]
