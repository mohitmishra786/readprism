"""Tests for server-side HTML sanitization (audit 06-7)."""

from __future__ import annotations

import pytest

from app.utils.sanitize import sanitize_stored_html


def test_strips_script_tags():
    out = sanitize_stored_html("<p>hi</p><script>alert(1)</script>")
    assert "<script" not in out.lower()
    assert "alert(1)" not in out
    assert "hi" in out


def test_strips_event_handlers():
    out = sanitize_stored_html('<img src="x" onerror="alert(1)">')
    assert "onerror" not in out.lower()


def test_strips_javascript_urls():
    out = sanitize_stored_html('<a href="javascript:alert(1)">click</a>')
    assert "javascript:" not in out.lower()
    assert "click" in out


def test_strips_iframe_and_object():
    out = sanitize_stored_html('<iframe src="evil"></iframe><object></object><p>ok</p>')
    assert "<iframe" not in out.lower()
    assert "<object" not in out.lower()
    assert "ok" in out


def test_preserves_safe_markup():
    out = sanitize_stored_html(
        "<p>Hello <strong>world</strong> <a href='https://x.com'>link</a></p>"
    )
    assert "<strong>" in out
    assert "world" in out
    assert "https://x.com" in out


def test_empty_input():
    assert sanitize_stored_html("") == ""


@pytest.mark.parametrize(
    "payload",
    [
        "<svg><script>alert(1)</script></svg>",
        '<p style="width: expression(alert(1))">x</p>',
        '<a href="javascript:alert(1)" onclick="alert(1)">x</a>',
        '<img src="x" onerror="alert(1)">',
        "<math><mi>x</mi><mglyph><script>alert(1)</script></mglyph></math>",
    ],
)
def test_xss_payloads_do_not_survive(payload):
    out = sanitize_stored_html(payload).lower()
    assert "<script" not in out
    assert "onerror" not in out
    assert "onclick" not in out
    assert "javascript:" not in out
    assert "expression(" not in out
    assert "<svg" not in out


def test_links_are_noopener():
    out = sanitize_stored_html('<a href="https://example.com">go</a>')
    assert "noopener" in out
    assert "noreferrer" in out


def test_email_template_escapes_item_html():
    from types import SimpleNamespace

    from app.services.digest.delivery import _fallback_html, _get_jinja_env

    content = SimpleNamespace(
        url='https://example.com/a?q="><script>alert(1)</script>',
        title="<script>alert(1)</script>",
        summary_brief='<img src=x onerror="alert(1)">',
    )
    sections = {"lead": [{"content": content}]}
    user = SimpleNamespace(email="reader@example.com")
    html = _fallback_html(user, sections)
    # The characters survive only as escaped text, so the mail client cannot parse a tag.
    assert "<script" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html

    content.author = None
    content.reading_time_minutes = None
    env = _get_jinja_env()
    rendered = env.get_template("digest_email.html").render(
        user=user,
        digest=SimpleNamespace(total_items=1),
        sections={"lead": [{"content": content, "why_ranked": ["semantic alignment"]}]},
        generated_at="September 24, 2026",
        preferences_url="https://example.com/preferences",
        unsubscribe_url="https://example.com/unsub",
        physical_address="",
    )
    assert "<script" not in rendered
    assert "<img" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "onerror=&#34;" in rendered or "onerror=&quot;" in rendered
