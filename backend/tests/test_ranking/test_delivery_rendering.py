"""Digest email rendering: escaping + working links (audit 04-6, 06-7, 08-5)."""

from __future__ import annotations

from app.models.content import ContentItem
from app.models.user import User
from app.services.digest.delivery import (
    _build_text_body,
    _fallback_html,
    _get_jinja_env,
    _top_signals,
)


def _sections_with(title: str, summary: str) -> dict:
    content = ContentItem(url="https://example.com/a", title=title, summary_brief=summary)
    return {"lead": [{"content": content, "why_ranked": ["matches your interests"]}]}


def test_fallback_html_escapes_content():
    """A malicious title/summary must not inject markup into the email."""
    sections = _sections_with("<script>alert(1)</script>", "<img src=x onerror=alert(1)>")
    html = _fallback_html(User(email="u@e.com", hashed_password="x"), sections)
    # The dangerous tags are escaped to inert text, never emitted as live markup.
    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html


def test_template_renders_with_unsubscribe_and_escapes():
    template = _get_jinja_env().get_template("digest_email.html")
    sections = _sections_with("<b>Title</b>", "safe summary")
    html = template.render(
        user=User(email="u@e.com", hashed_password="x"),
        digest=type("D", (), {"total_items": 1})(),
        sections=sections,
        generated_at="July 21, 2026",
        preferences_url="https://app.example.com/preferences",
        unsubscribe_url="https://api.example.com/api/v1/digest/unsubscribe?uid=1&token=abc",
        physical_address="123 Main St",
    )
    assert "https://api.example.com/api/v1/digest/unsubscribe" in html
    assert "https://app.example.com/preferences" in html
    assert "123 Main St" in html
    assert "&lt;b&gt;Title&lt;/b&gt;" in html  # title autoescaped


def test_text_body_includes_links():
    sections = _sections_with("Title", "Summary")
    text = _build_text_body(
        User(email="u@e.com", hashed_password="x"),
        sections,
        "https://app/preferences",
        "https://api/unsub",
    )
    assert "https://app/preferences" in text
    assert "https://api/unsub" in text
    assert "Title" in text


def test_top_signals_returns_labels():
    labels = _top_signals({"semantic": 0.8, "source_trust": 0.6, "novelty": 0.1})
    assert labels
    assert any("interest" in label for label in labels)
