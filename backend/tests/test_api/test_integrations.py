"""Tests for the PKM integration export — Obsidian Markdown rendering.

The Obsidian path is pure (file generation), so it's directly unit-testable.
Notion/Readwise are HTTP-bound and covered by their error-path validation only.
"""
from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock

from app.services.integrations.export import _slugify, _to_markdown


def _make_content(
    title="How Distributed Consensus Actually Works",
    url="https://example.com/post",
    author="Jane Doe",
    summary_brief="A practical guide to Raft and Paxos.",
    full_text="Consensus is harder than it looks.\n\nHere is why.",
):
    c = MagicMock()
    c.title = title
    c.url = url
    c.author = author
    c.summary_brief = summary_brief
    c.summary_detailed = None
    c.full_text = full_text
    c.reading_time_minutes = 8
    return c


def _make_interaction():
    i = MagicMock()
    i.saved_read_at = datetime(2026, 7, 3, tzinfo=UTC)
    return i


def test_slugify_makes_filename_safe():
    assert _slugify("How/Consensus Works: A Guide") == "How-Consensus-Works-A-Guide"
    assert _slugify("  multiple   spaces  ") == "multiple-spaces"
    assert _slugify("") == "untitled"


def test_to_markdown_includes_frontmatter_and_link():
    filename, body = _to_markdown(_make_content(), _make_interaction())
    assert filename.endswith(".md")
    assert body.startswith("---")
    # Values are now YAML-quoted (safe escaping).
    assert 'source: "https://example.com/post"' in body
    assert 'author: "Jane Doe"' in body
    assert "# How Distributed Consensus Actually Works" in body


def test_to_markdown_includes_summary_as_blockquote():
    _, body = _to_markdown(_make_content(), _make_interaction())
    assert "> A practical guide to Raft and Paxos." in body


def test_to_markdown_includes_full_text_when_present():
    _, body = _to_markdown(_make_content(), _make_interaction())
    assert "Consensus is harder than it looks." in body


def test_to_markdown_falls_back_to_link_when_no_full_text():
    content = _make_content(full_text=None)
    _, body = _to_markdown(content, _make_interaction())
    assert "Read original" in body
    assert "https://example.com/post" in body


def test_to_markdown_truncates_long_title_in_filename():
    long_title = "A " * 100  # 200 chars
    content = _make_content(title=long_title)
    filename, _ = _to_markdown(content, _make_interaction())
    # Slug is capped at 80 chars before the .md extension.
    assert len(filename) <= 80 + len(".md")
