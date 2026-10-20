"""Digest email: snapshot and client-compatibility checks (#217).

The snapshot (tests/fixtures/email/digest_email.html) is what reviewers and
the browser rendering check look at; regenerate it on purpose with
UPDATE_SNAPSHOTS=1 after an intended template change.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from app.services.digest.delivery import _build_text_body, _get_jinja_env

SNAPSHOT = Path(__file__).resolve().parents[1] / "fixtures" / "email" / "digest_email.html"


def _content(title, *, source="llm", author="Ada Lovelace", minutes=6, brief="A brief summary."):
    return SimpleNamespace(
        title=title,
        author=author,
        reading_time_minutes=minutes,
        summary_brief=brief,
        summary_source=source,
        url="https://example.com/x",
    )


def _row(n, content, **extra):
    base = f"https://rp.example/api/v1/digest/e/{{}}/item{n}?sig=s"
    return {
        "content": content,
        "why_ranked": ["matches your interest in compilers", "from a source you trust"],
        "open_url": base.format("open"),
        "up_url": base.format("up"),
        "down_url": base.format("down"),
        "save_url": base.format("save"),
        "discovered_via": None,
        **extra,
    }


def context() -> dict:
    sections = {
        "lead": [
            _row(1, _content("How compilers lower loops")),
            _row(2, _content("Postgres vacuum, explained", source="extractive", author=None)),
        ],
        # A long title: the phone rendering check must still not scroll sideways.
        "deep_reads": [
            _row(
                3,
                _content(
                    "A long read on how operating system schedulers balance latency, "
                    "throughput and fairness across very different workloads",
                    minutes=24,
                ),
            )
        ],
        "discovery": [
            _row(4, _content("An adjacent idea"), discovered_via="a link in Simon Willison's blog")
        ],
    }
    return {
        "user": SimpleNamespace(display_name="Reader", email="r@example.com"),
        "digest": SimpleNamespace(total_items=4),
        "sections": sections,
        "generated_at": datetime(2026, 10, 20, tzinfo=UTC).strftime("%B %d, %Y"),
        "preferences_url": "https://rp.example/preferences",
        "unsubscribe_url": "https://rp.example/unsubscribe?t=x",
        "physical_address": "1 Example Street, Example City",
        "dead_sources": ["Old Blog"],
        "sources_url": "https://rp.example/sources",
        "lead_title": "How compilers lower loops",
        "logo_url": (
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAABg0lEQVR4nOyXP06EQBSH"
            "3zALAkew0MZCuy1NDJTa7gUsbOy8ADQ2EI+wsfUC2hlbKCy5gsaYbG8CFfjeRDaEaJg/hmn2SzYPdovfN8PsDG8BA3zfv2"
            "SMrfDyFOs+/CNd131iecX62DTNQ/89+wk+dBznHi/PYR5e2ra9RpE3IRAEQYkjPoMZwZko67qOOI7+Ckd/AzODAz7gnL9z"
            "z/Pu8P4ILIAS/gLrEuyxZGEYdmARByyzAAPSNBU1yzLQRVuAwpMk2d7rSnDXdW9BkXF4FEW0oqEoClBFWWAcbiqhJEDB/XMn"
            "aNrLshThuhLSAhQ8DM/zXHwojEJ1JaQExtNOwcNFZyIxKTAVbiphfSOanAHZkcnOlLKAjIRuuLRAL0HEcbyV6O91wwnl0/Cv"
            "jUgnnFDeCcePwyRcS+A3Cd1wQvs0HAaaHMe7NyIS2IA9NiRQgT0qEliDPdaiNcOF+IzlAmYEW7MnbM1WQgC7o2Nskyr8b+/B"
            "DGD4F5YTFPhgwx9stOffAAAA//+FGy1iAAAABklEQVQDALAoxcJeqbI7AAAAAElFTkSuQmCC"
        ),
    }


def render() -> str:
    return _get_jinja_env().get_template("digest_email.html").render(**context())


def test_matches_the_snapshot():
    html = render()
    if os.environ.get("UPDATE_SNAPSHOTS") or not SNAPSHOT.exists():
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(html)
    assert html == SNAPSHOT.read_text(), "template changed: review, then UPDATE_SNAPSHOTS=1"


def test_supports_light_and_dark_mode():
    html = render()
    assert '<meta name="color-scheme" content="light dark">' in html
    assert "@media (prefers-color-scheme: dark)" in html


def test_color_scheme_meta_tags_present():
    html = render()
    assert '<meta name="color-scheme" content="light dark">' in html
    assert '<meta name="supported-color-schemes" content="light dark">' in html


def test_no_blue_colors_in_rendered_html():
    html = render()
    assert "#1d4ed8" not in html
    assert "#2563eb" not in html
    assert "#93c5fd" not in html


def test_every_action_link_preserved():
    html = render()
    hrefs = set(re.findall(r'href="([^"]*)"', html))
    for n in range(1, 5):
        for action in ("open", "up", "down", "save"):
            expected = f"https://rp.example/api/v1/digest/e/{action}/item{n}?sig=s"
            assert expected in hrefs, f"Missing action link: {expected}"
    for expected in (
        "https://rp.example/preferences",
        "https://rp.example/unsubscribe?t=x",
        "https://rp.example/sources",
    ):
        assert expected in hrefs, f"Missing footer link: {expected}"


def test_layout_survives_clients_without_css_layout():
    """Outlook's Word engine: tables for layout, inline styles on every link."""
    html = render()
    assert html.count('role="presentation"') >= 4
    links = re.findall(r"<a [^>]*>", html)
    assert links and all('style="' in a for a in links)


def test_preheader_previews_the_top_story():
    html = render()
    preheader = re.search(r'<div style="display:none[^>]*>(.*?)</div>', html, re.S).group(1)
    assert "4 reads ranked for you: How compilers lower loops" in preheader


def test_every_item_has_read_rate_and_save_actions():
    html = render()
    for n in range(1, 5):
        for action in ("open", "up", "down", "save"):
            assert f"/e/{action}/item{n}?" in html
    assert html.count(">Read in Weirling</a>") == 4


def test_labels_ai_summaries_and_discovery_sources():
    html = render()
    assert html.count(">AI summary</span>") == 3  # the extractive one has no label
    assert "via a link in Simon Willison&#39;s blog" in html


def test_footer_links_and_dead_source_fix():
    html = render()
    for url in (
        "https://rp.example/preferences",
        "https://rp.example/unsubscribe?t=x",
        "https://rp.example/sources",
    ):
        assert f'href="{url}"' in html
    assert "1 Example Street" in html


def test_plain_text_part_has_every_item():
    ctx = context()
    text = _build_text_body(
        ctx["user"], ctx["sections"], ctx["preferences_url"], ctx["unsubscribe_url"]
    )
    for title in ("How compilers lower loops", "Postgres vacuum, explained", "An adjacent idea"):
        assert title in text
    assert "Unsubscribe: https://rp.example/unsubscribe?t=x" in text


def test_send_script_mails_the_reference_snapshot(monkeypatch):
    """#217: the manual client check sends exactly the snapshot under test."""
    import asyncio
    import importlib.util

    script = Path(__file__).resolve().parents[2] / "scripts" / "send_test_digest_email.py"
    spec = importlib.util.spec_from_file_location("send_test_digest_email", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    sent: list[dict] = []

    async def fake_send(**kwargs):
        sent.append(kwargs)
        return kwargs["to"] != "bounce@example.com"

    monkeypatch.setattr("app.utils.email.send_email", fake_send)
    assert asyncio.run(module.main(["a@example.com"])) == 0
    assert sent[0]["html_body"] == SNAPSHOT.read_text()
    assert asyncio.run(module.main(["bounce@example.com"])) == 1
