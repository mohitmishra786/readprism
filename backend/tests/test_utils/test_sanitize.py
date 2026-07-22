"""Tests for server-side HTML sanitization (audit 06-7)."""

from __future__ import annotations

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
