"""Large OPML imports run in the background with progress (#202)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.models.source import Source
from app.models.user import User
from tests.conftest import TestingSessionLocal


def _opml(n: int) -> str:
    rows = "".join(
        f'<outline type="rss" text="F{i}" xmlUrl="https://big{i}.example.com/rss"/>'
        for i in range(n)
    )
    return f'<?xml version="1.0"?><opml version="1.0"><body><outline text="All">{rows}</outline></body></opml>'


@pytest.mark.asyncio
async def test_2000_outline_opml_is_queued_and_imports_with_progress(client, db_session):
    email = f"big{uuid.uuid4().hex[:6]}@example.com"
    reg = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "TestPass123!"}
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    user_id = (await db_session.execute(select(User.id).where(User.email == email))).scalar_one()

    with patch("app.workers.tasks.import_jobs.run_opml_import.delay") as enqueue:
        resp = await client.post(
            "/api/v1/sources/import-opml-v2",
            files={"file": ("feedly.opml", _opml(2000), "text/xml")},
            headers=headers,
        )
    body = resp.json()
    assert resp.status_code == 200 and body["queued"] is True and body["total"] == 2000
    job_id = body["job_id"]
    enqueue.assert_called_once_with(job_id)
    # Nothing inserted inside the request.
    count = select(func.count()).select_from(Source).where(Source.user_id == user_id)
    assert (await db_session.execute(count)).scalar() == 0
    first = (await client.get(f"/api/v1/sources/import-jobs/{job_id}", headers=headers)).json()
    assert first["status"] == "queued" and first["progress"] == 0

    from app.workers.tasks.import_jobs import _run_opml_import

    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.workers.tasks.ingest_feeds.ingest_user_sources.delay") as fetch_now,
    ):
        result = await _run_opml_import(job_id)

    assert result == {"status": "done", "created": 2000}
    fetch_now.assert_called_once_with(str(user_id))
    db_session.expire_all()
    assert (await db_session.execute(count)).scalar() == 2000
    done = (await client.get(f"/api/v1/sources/import-jobs/{job_id}", headers=headers)).json()
    assert done["status"] == "done" and done["progress"] == 1.0 and done["created"] == 2000


@pytest.mark.asyncio
async def test_small_imports_still_run_inline(client):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": f"sm{uuid.uuid4().hex[:6]}@example.com", "password": "TestPass123!"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    with patch("app.workers.tasks.ingest_feeds.ingest_user_sources.delay"):
        resp = await client.post(
            "/api/v1/sources/import-opml-v2",
            files={"file": ("small.opml", _opml(5), "text/xml")},
            headers=headers,
        )
    assert resp.json()["queued"] is False and resp.json()["created"] == 5
