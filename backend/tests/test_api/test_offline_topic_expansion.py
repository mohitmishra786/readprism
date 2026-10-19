"""Interest expansion with no LLM key (#196)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.services.cold_start.taxonomy import _topics, expand


def test_rust_and_postgres_internals_expand_to_sensible_chips():
    chips = expand("rust, postgres internals")
    assert len(chips) >= 6
    assert {"Rust", "PostgreSQL", "Database internals"} <= set(chips)
    assert {"Query planning", "MVCC"} & set(chips)


def test_one_loose_word_does_not_drag_in_unrelated_topics():
    chips = expand("language design")
    assert chips[0] == "Programming language design"
    assert "UI design" not in chips


def test_unknown_text_gives_nothing_so_keywords_take_over():
    assert expand("zxqv flurble") == []


def test_every_related_topic_is_a_real_topic():
    labels = {t["label"] for t in _topics()}
    missing = {r for t in _topics() for r in t.get("related", []) if r not in labels}
    assert not missing, missing


@pytest.mark.asyncio
async def test_expand_endpoint_without_an_llm_key(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_api_key", "")
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": f"tx{uuid.uuid4().hex[:6]}@example.com", "password": "TestPass123!"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    with patch(
        "app.services.summarization.groq_client.LLMSummarizer.expand_interests",
        side_effect=Exception("no key"),
    ):
        resp = await client.post(
            "/api/v1/onboarding/expand-interests",
            json={"interest_text": "rust, postgres internals, and my homelab"},
            headers=headers,
        )
    topics = resp.json()["topics"]
    assert len(topics) >= 6 and "PostgreSQL" in topics and "Self-hosting" in topics
