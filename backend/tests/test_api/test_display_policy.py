"""Hosted content display policy (#177)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.models.content import ContentItem

BODY = "Paragraph of the article. " * 80


@pytest.fixture
def mode(monkeypatch):
    from app.config import get_settings

    def set_mode(deployment: str, reader: str = "auto"):
        monkeypatch.setattr(get_settings(), "deployment_mode", deployment)
        monkeypatch.setattr(get_settings(), "reader_full_text", reader)
        monkeypatch.setattr(get_settings(), "registration_mode", "open")
        monkeypatch.setattr(get_settings(), "email_verification", "off")

    return set_mode


async def _reader(client):
    data = {"email": f"dp{uuid.uuid4().hex[:6]}@example.com", "password": "TestPass123!"}
    reg = await client.post("/api/v1/auth/register", json=data)
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    return headers, uuid.UUID(me["id"])


async def _item(db_session, method: str | None, *, owner=None, summary_source="llm") -> ContentItem:
    item = ContentItem(
        url=f"https://pub.example/{uuid.uuid4().hex}",
        title="T",
        full_text=BODY,
        extraction_method=method,
        owner_user_id=owner,
        summary_brief="Short summary.",
        summary_source=summary_source,
    )
    db_session.add(item)
    await db_session.commit()
    return item


async def _get(client, headers, item):
    resp = await client.get(f"/api/v1/content/{item.id}", headers=headers)
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.asyncio
async def test_hosted_reader_never_shows_page_extracted_text(client, db_session, mode):
    mode("hosted")
    headers, me = await _reader(client)

    for method in ("trafilatura", "readability", "playwright", None):
        body = await _get(client, headers, await _item(db_session, method))
        assert body["full_text"] is None and body["full_text_withheld"] is True, method
        assert body["summary_brief"] == "Short summary." and body["summary_source"] == "llm"

    feed = await _get(client, headers, await _item(db_session, "feed"))
    assert feed["full_text"] == BODY and feed["full_text_withheld"] is False

    # The reader's own save (extension, newsletter) is theirs to read in full.
    own = await _get(client, headers, await _item(db_session, "trafilatura", owner=me))
    assert own["full_text"] == BODY


@pytest.mark.asyncio
async def test_selfhost_shows_everything_unless_overridden(client, db_session, mode):
    mode("selfhost")
    headers, _ = await _reader(client)
    item = await _item(db_session, "trafilatura")
    assert (await _get(client, headers, item))["full_text"] == BODY

    mode("selfhost", "feed_only")
    assert (await _get(client, headers, item))["full_text_withheld"] is True
    mode("hosted", "all")
    assert (await _get(client, headers, item))["full_text"] == BODY


def test_email_text_labels_ai_summaries():
    from app.services.digest.delivery import _build_text_body

    def entry(source):
        content = SimpleNamespace(
            title="T", url="https://x", summary_brief="Brief.", summary_source=source
        )
        return {
            "content": content,
            "open_url": "o",
            "up_url": "u",
            "down_url": "d",
            "save_url": "s",
        }

    user = SimpleNamespace(display_name="R", email="r@example.com")
    text = _build_text_body(
        user, {"lead": [entry("llm"), entry("extractive")]}, "https://p", "https://u"
    )
    assert "AI summary: Brief." in text
    assert text.count("AI summary") == 1
