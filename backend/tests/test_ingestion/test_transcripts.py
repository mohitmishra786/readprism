"""Podcast transcripts (EC-08): cleaning + ingest wiring."""

from __future__ import annotations

import re

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
