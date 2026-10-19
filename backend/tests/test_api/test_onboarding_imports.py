"""One-step imports: Feedly/Inoreader OPML, Pocket HTML, CSV (#150)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.source import Source
from app.models.user import User


async def _login(client, db_session):
    email = f"im{uuid.uuid4().hex[:6]}@example.com"
    reg = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "TestPass123!"}
    )
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}, user.id


def _feedly_opml(n: int) -> str:
    folders = ["Tech", "Science", "Design", "News"]
    body = "".join(
        f'<outline text="{folder}" title="{folder}">'
        + "".join(
            f'<outline type="rss" text="Feed {i}" title="Feed {i}" '
            f'xmlUrl="https://feed{i}.example.com/rss" htmlUrl="https://feed{i}.example.com/"/>'
            for i in range(n)
            if i % len(folders) == k
        )
        + "</outline>"
        for k, folder in enumerate(folders)
    )
    return f'<?xml version="1.0"?><opml version="1.0"><head><title>Feedly</title></head><body>{body}</body></opml>'


@pytest.mark.asyncio
async def test_200_feed_feedly_opml_imports(client, db_session):
    headers, user_id = await _login(client, db_session)
    with patch("app.workers.tasks.ingest_feeds.ingest_user_sources.delay"):
        resp = await client.post(
            "/api/v1/sources/import-opml-v2",
            files={"file": ("feedly.opml", _feedly_opml(200), "text/xml")},
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 200 and resp.json()["errors"] == []
    rows = list(
        (await db_session.execute(select(Source).where(Source.user_id == user_id))).scalars()
    )
    assert len(rows) == 200
    assert {tag for s in rows for tag in (s.tags or [])} == {"Tech", "Science", "Design", "News"}


POCKET = """<!DOCTYPE html><html><head><title>Pocket Export</title></head><body>
<h1>Unread</h1><ul>
<li><a href="https://blog.example.com/a" time_added="1700000000" tags="rust,compilers">A on Rust</a></li>
<li><a href="javascript:alert(1)" time_added="1700000001" tags="">Bad row</a></li>
</ul><h1>Read Archive</h1><ul>
<li><a href="https://blog.example.com/b" time_added="1690000000" tags="">B, untagged</a></li>
</ul></body></html>"""


@pytest.mark.asyncio
async def test_pocket_export_imports_urls_titles_tags_and_reports_bad_rows(client, db_session):
    headers, user_id = await _login(client, db_session)
    resp = await client.post(
        "/api/v1/sources/import-saved",
        files={"file": ("ril_export.html", POCKET, "text/html")},
        headers=headers,
    )
    body = resp.json()
    assert resp.status_code == 200 and body["kind"] == "pocket"
    assert body["created"] == 2
    assert body["errors"] == [
        {"row": 2, "url": "javascript:alert(1)", "error": "not an http(s) URL"}
    ]

    saved = (
        await db_session.execute(
            select(ContentItem, UserContentInteraction)
            .join(UserContentInteraction, UserContentInteraction.content_item_id == ContentItem.id)
            .where(UserContentInteraction.user_id == user_id)
        )
    ).all()
    by_url = {c.url: (c, ix) for c, ix in saved}
    item, ix = by_url["https://blog.example.com/a"]
    assert item.title == "A on Rust" and ix.saved and ix.tags == ["rust", "compilers"]
    assert by_url["https://blog.example.com/b"][1].tags is None


@pytest.mark.asyncio
async def test_generic_csv_is_detected_and_a_bad_row_is_not_fatal(client, db_session):
    headers, _ = await _login(client, db_session)
    csv_text = (
        "url,title,tags\nhttps://x.example/1,One,a;b\nnot a url,Two,\nhttps://x.example/3,Three,\n"
    )
    resp = await client.post(
        "/api/v1/sources/import-saved",
        files={"file": ("export.csv", csv_text, "text/csv")},
        headers=headers,
    )
    body = resp.json()
    assert body["kind"] == "csv" and body["created"] == 2
    assert [e["row"] for e in body["errors"]] == [2]


def test_csv_shapes_are_detected():
    from app.services.ingestion.importers import detect_csv_kind

    assert detect_csv_kind("URL,Title,Selection,Folder\n") == "instapaper"
    assert detect_csv_kind("url,title,excerpt,tags\n") == "raindrop"
    assert detect_csv_kind("Highlight,Title,URL\n") == "readwise"
    assert detect_csv_kind("link,title\n") == "csv"
