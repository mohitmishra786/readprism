"""Podcast transcripts (EC-08): cleaning + ingest wiring."""

from __future__ import annotations

import re

import pytest

from app.services.ingestion.transcripts import clean_transcript


def test_vtt_cues_are_stripped():
    raw = "\n".join(
        [
            "WEBVTT",
            "",
            "1",
            "00:00:01.000 --> 00:00:03.000",
            "Welcome back to the show.",
            "",
            "2",
            "00:00:03.000 --> 00:00:06.000",
            "Today we talk about <b>vector databases</b>.",
        ]
    )
    cleaned = clean_transcript(raw)
    assert cleaned == "Welcome back to the show. Today we talk about vector databases."


def test_srt_cues_are_stripped():
    raw = "\n".join(
        [
            "1",
            "00:00:01,000 --> 00:00:03,000",
            "First line.",
            "2",
            "00:00:03,000 --> 00:00:05,000",
            "Second line.",
        ]
    )
    cleaned = clean_transcript(raw)
    assert cleaned == "First line. Second line."


def test_plain_text_passes_through_with_normalization():
    assert clean_transcript("  hello   world  \n\n next ") == "hello world next"
    assert re.fullmatch(r"\s*", "") is not None


def test_vtt_range_without_hours_is_stripped():
    raw = "\n".join(
        [
            "WEBVTT",
            "",
            "00:01.000 --> 00:03.000",
            "Welcome back.",
        ]
    )
    assert clean_transcript(raw) == "Welcome back."


def test_note_and_style_blocks_are_skipped_whole():
    raw = "\n".join(
        [
            "WEBVTT",
            "",
            "NOTE this is a multi-line",
            "comment block that must vanish",
            "",
            "STYLE",
            "::cue { color: red; }",
            "",
            "1",
            "00:00:01.000 --> 00:00:03.000",
            "Actual cue text.",
        ]
    )
    assert clean_transcript(raw) == "Actual cue text."


SHOW_NOTES = (
    "Show notes. Sponsored by Example Hosting. Follow us on social media for more episodes."
)
TRANSCRIPT = (
    "Welcome to the episode about vacuum in Postgres. Vacuum removes dead tuples left by updates. "
    "Autovacuum runs this cleanup in the background on busy tables. "
    "Freezing old rows prevents transaction id wraparound."
)


@pytest.mark.asyncio
async def test_podcast_items_with_transcripts_get_transcript_based_summaries(db_session):
    """#252: ingest -> transcript text stored -> the summary comes from it."""
    import random
    import uuid
    from unittest.mock import AsyncMock, patch

    from sqlalchemy import select

    from app.models.content import ContentItem
    from app.models.source import Source
    from app.models.user import User
    from app.services.ingestion.rss_parser import RawContentItem
    from app.workers.tasks.compute_embeddings import _compute_embedding_async
    from app.workers.tasks.ingest_feeds import _ingest_source
    from tests.conftest import TestingSessionLocal

    user = User(email=f"pod{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    src = Source(
        user_id=user.id,
        url="https://pod.example/",
        feed_url="https://pod.example/rss",
        name="DB Pod",
    )
    db_session.add(src)
    await db_session.commit()
    episode = RawContentItem(
        url=f"https://pod.example/ep/{uuid.uuid4().hex}",
        title="Postgres vacuum",
        full_text=SHOW_NOTES,
        transcript_url="https://pod.example/ep1.vtt",
    )
    with (
        patch(
            "app.services.ingestion.dispatcher.dispatch_source", AsyncMock(return_value=[episode])
        ),
        patch(
            "app.services.ingestion.transcripts.fetch_transcript_text",
            AsyncMock(return_value=TRANSCRIPT),
        ),
    ):
        ids = await _ingest_source(src, db_session, random.Random(1))
    await db_session.commit()
    assert len(ids) == 1

    with patch("app.database.AsyncSessionLocal", TestingSessionLocal):
        await _compute_embedding_async(ids[0])
    db_session.expire_all()
    item = (
        await db_session.execute(select(ContentItem).where(ContentItem.id == ids[0]))
    ).scalar_one()
    assert item.transcript_url == "https://pod.example/ep1.vtt"
    assert item.full_text.startswith(TRANSCRIPT)
    assert "Vacuum" in item.summary_brief or "vacuum" in item.summary_brief
    assert "Sponsored" not in item.summary_brief


@pytest.mark.asyncio
async def test_the_model_is_told_it_is_a_transcript(monkeypatch):
    import uuid
    from unittest.mock import patch

    from app.config import get_settings
    from app.models.content import ContentItem
    from app.services.summarization.groq_client import TRANSCRIPT_INSTRUCTION
    from app.services.summarization.lazy import ensure_llm_summaries

    monkeypatch.setattr(get_settings(), "llm_api_key", "test-key")
    prompts: list[str] = []

    async def fake(self, *, model, system, user, max_tokens):
        prompts.append(user)
        return None

    items = [
        ContentItem(
            id=uuid.uuid4(),
            url="https://pod.example/1",
            title="t",
            full_text=TRANSCRIPT,
            transcript_url="https://pod.example/1.vtt",
            summary_source="extractive",
        ),
        ContentItem(
            id=uuid.uuid4(),
            url="https://blog.example/1",
            title="t",
            full_text=TRANSCRIPT,
            summary_source="extractive",
        ),
    ]
    with (
        patch("app.services.llm.client.LLMClient.complete_json", fake),
        patch("app.services.summarization.summarizer._llm_summarizer", None),
    ):
        await ensure_llm_summaries(items)
    assert sum(TRANSCRIPT_INSTRUCTION in p for p in prompts) == 1
