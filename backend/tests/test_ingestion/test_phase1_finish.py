"""Phase 1 remainder: identity, extraction, newsletters, OPML, retention."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.ingestion.backfill import cap_per_source, newest_n
from app.services.ingestion.extract import extract_html
from app.services.ingestion.golden import evaluate
from app.services.ingestion.identity import apply_permanent_redirect, canonical_from_html
from app.services.ingestion.importers import import_csv, import_opml_starred
from app.services.ingestion.metadata import extract_metadata
from app.services.ingestion.newsletter_parse import (
    parse_cloudflare,
    parse_imap_batch,
    parse_postmark,
    parse_resend,
    parse_rfc822,
    recipient_token,
    unwrap_link,
    verify_body_hmac,
)
from app.services.ingestion.observe import ingestion_report
from app.services.ingestion.opml_io import export_opml, parse_opml, plan_import
from app.services.ingestion.retention import retention_plan, storage_stats
from app.services.ingestion.robots import domain_denied, host_wait, robots_decision
from app.services.ingestion.rsshub import candidate_urls, rsshub_is_healthy
from app.services.ingestion.simhash import is_near_duplicate, simhash_text


def test_simhash_matches_same_text_and_rejects_a_different_story():
    left = simhash_text("rust async runtimes and borrow checking details")
    assert is_near_duplicate(left, simhash_text("rust async runtimes and borrow checking details"))
    other = simhash_text("sourdough hydration and oven spring techniques")
    assert not is_near_duplicate(left, other)


def test_canonical_link_and_og_url_replace_the_page_url():
    html = '<html><head><link rel="canonical" href="https://1.1.1.1/posts/a"></head></html>'
    assert (
        canonical_from_html(html, "https://1.1.1.1/posts/a?utm_source=x")
        == "https://1.1.1.1/posts/a"
    )
    og = '<html><head><meta property="og:url" content="https://1.1.1.1/b"></head></html>'
    assert canonical_from_html(og, "https://1.1.1.1/tracker") == "https://1.1.1.1/b"
    private = '<html><head><link rel="canonical" href="http://127.0.0.1/secret"></head></html>'
    assert canonical_from_html(private, "https://1.1.1.1/page") is None


def test_permanent_redirect_rewrites_only_the_fetched_url():
    source = SimpleNamespace(feed_url="https://1.1.1.1/old.xml", url="https://1.1.1.1/")
    apply_permanent_redirect(source, "https://1.1.1.1/old.xml", "https://1.0.0.1/new.xml")
    assert source.feed_url == "https://1.0.0.1/new.xml"
    assert source.url == "https://1.1.1.1/"


def test_extraction_cascade_and_unrankable_pages():
    article = "<html><body><article><p>" + ("word " * 90) + "</p></article></body></html>"
    extracted = extract_html(article, "https://1.1.1.1/a", feed_text="short")
    assert extracted.method in {"trafilatura", "readability"}
    assert extracted.rankable
    feed = extract_html("<html></html>", feed_text=" ".join(f"w{i}" for i in range(90)))
    assert feed.method == "feed"
    product = '<html><head><meta property="og:type" content="product"></head><body>Add to cart</body></html>'
    assert not extract_html(product).rankable
    failed = extract_html('<html><body><div id="app"></div><script>boot()</script></body></html>')
    assert failed.method == "failed"
    rendered = "<html><body><article><p>" + ("rendered " * 50) + "</p></article></body></html>"
    played = extract_html(failed.text, rendered_html=rendered)
    assert played.method == "playwright"


def test_golden_article_f1_clears_the_gate():
    report = evaluate()
    assert report["articles"] == 80
    assert report["word_f1"] >= 0.90
    assert report["snippet_recall"] >= 0.90
    assert report["listings_unrankable"] == report["listings"]


def test_metadata_prefers_json_ld_and_labels_paywalls():
    html = """
    <html lang="en"><head>
      <script type="application/ld+json">
        {"author": {"name": "Ada"}, "datePublished": "2026-01-02T00:00:00Z",
         "image": "https://1.1.1.1/a.jpg", "isAccessibleForFree": false}
      </script>
    </head><body><p>The and of to a long note.</p></body></html>
    """
    meta = extract_metadata(html, text="The and of to a long note for readers.")
    assert meta.author == "Ada"
    assert meta.language == "en"
    assert meta.lead_image_url == "https://1.1.1.1/a.jpg"
    assert meta.paywalled
    assert meta.reading_time_minutes == 1


def test_rsshub_is_off_until_configured():
    assert candidate_urls("https://x.com/someuser", base="") == []
    assert candidate_urls("https://x.com/someuser", base="https://rsshub.example") == [
        "https://rsshub.example/twitter/user/someuser"
    ]
    assert candidate_urls("https://www.linkedin.com/in/ada", base="https://rsshub.example") == []


@pytest.mark.asyncio
async def test_rsshub_health_fetches_only_when_base_is_set(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "rsshub_base_url", "")
    calls: list[str] = []

    async def fetch(url: str) -> int:
        calls.append(url)
        return 200

    assert await rsshub_is_healthy(fetch) is None
    assert calls == []
    monkeypatch.setattr(get_settings(), "rsshub_base_url", "https://rsshub.example")
    assert await rsshub_is_healthy(fetch) is True
    assert calls == ["https://rsshub.example/"]


def test_robots_policy():
    assert robots_decision("absent", "", "https://1.1.1.1/a", fail_open=False)
    assert not robots_decision("error", "", "https://1.1.1.1/a", fail_open=False)
    assert robots_decision("error", "", "https://1.1.1.1/a", fail_open=True)
    body = "User-agent: *\nDisallow: /private"
    assert not robots_decision("ok", body, "https://1.1.1.1/private/a", fail_open=False)
    assert robots_decision("ok", body, "https://1.1.1.1/public", fail_open=False)
    assert domain_denied("https://news.example.com/a", "example.com")
    assert not domain_denied("https://1.1.1.1/a", "example.com")
    assert host_wait(None, 10) == 0
    assert host_wait(9.5, 10, gap_seconds=1) == pytest.approx(0.5)


def test_backfill_keeps_newest_and_digest_caps_a_source():
    old = SimpleNamespace(published_at=datetime(2020, 1, 1, tzinfo=UTC), source_id="s")
    new = SimpleNamespace(published_at=datetime(2026, 1, 1, tzinfo=UTC), source_id="s")
    other = SimpleNamespace(published_at=datetime(2026, 1, 2, tzinfo=UTC), source_id="t")
    kept = newest_n([old, new], 1)
    assert kept == [new]
    capped = cap_per_source([new, old, other], 1)
    assert capped == [new, other]


def test_retention_plan_and_storage():
    now = datetime(2026, 9, 25, tzinfo=UTC)
    rows = [
        {
            "id": "old",
            "source_id": "s",
            "fetched_at": now - timedelta(days=100),
            "text_length": 800,
        },
        {"id": "new", "source_id": "s", "fetched_at": now, "text_length": 100},
        {"id": "extra", "source_id": "s", "fetched_at": now - timedelta(days=1), "text_length": 10},
    ]
    plan = retention_plan(rows, now=now, retention_days=90, per_source_cap=1, excerpt_chars=500)
    assert plan["prune_full_text"] == ["old"]
    assert set(plan["over_cap"]) == {"old", "extra"}
    stats = storage_stats(rows)
    assert stats["items"] == 3
    assert stats["full_text_chars"] == 910


def test_ingestion_report_rates_and_lag():
    sources = [
        SimpleNamespace(is_active=True, feed_status="healthy"),
        SimpleNamespace(is_active=True, feed_status="dead"),
    ]
    fetched = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    items = [
        SimpleNamespace(
            extraction_method="feed",
            fetched_at=fetched,
            scored_at=fetched + timedelta(seconds=30),
        ),
        SimpleNamespace(extraction_method="failed", fetched_at=fetched, scored_at=None),
    ]
    report = ingestion_report(sources, items)
    assert report["fetch_success_rate"] == 0.5
    assert report["extraction_by_method"]["failed"] == 1
    assert report["ingest_to_scored_p50_seconds"] == 30


def test_opml_tags_duplicates_and_round_trip():
    text = """<?xml version="1.0"?>
    <opml version="2.0"><body>
      <outline text="Tech">
        <outline type="rss" text="One" xmlUrl="https://1.1.1.1/one.xml"/>
        <outline type="rss" text="One again" xmlUrl="https://1.1.1.1/one.xml"/>
      </outline>
      <outline type="rss" text="Loose" xmlUrl="https://1.0.0.1/loose.xml"/>
    </body></opml>
    """
    feeds = parse_opml(text)
    assert len(feeds) == 2
    assert feeds[0].tags == ["Tech"]
    exported = export_opml(feeds)
    again = parse_opml(exported)
    assert {feed.url for feed in again} == {feed.url for feed in feeds}
    plan = plan_import(text, {"https://1.1.1.1/one.xml"})
    assert plan.created == 1
    assert plan.skipped == 1
    assert plan.queued is False
    big = ["<opml version='2.0'><body>"]
    for index in range(201):
        big.append(f'<outline type="rss" text="F{index}" xmlUrl="https://1.1.1.1/f{index}.xml"/>')
    big.append("</body></opml>")
    assert plan_import("".join(big), set()).queued is True


def test_saved_imports_flag_origin_and_a_positive_save():
    opml = """<opml version="2.0"><body>
      <outline text="starred" type="rss" xmlUrl="https://1.1.1.1/star.xml" category="starred"/>
    </body></opml>"""
    starred = import_opml_starred(opml)
    assert starred and starred[0].origin == "import" and starred[0].saved
    csv_text = "URL,Title,Selection\nhttps://1.1.1.1/a,Hello,note\n"
    instapaper = import_csv(csv_text, "instapaper")
    assert instapaper[0].title == "Hello"
    rain = import_csv("url,title,excerpt\nhttps://1.1.1.1/b,Rain,ex\n", "raindrop")
    wise = import_csv("URL,Title,Highlight\nhttps://1.1.1.1/c,Wise,hl\n", "readwise")
    assert rain[0].url.endswith("/b")
    assert wise[0].note == "hl"


def _signed(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_provider_signatures_fail_closed_and_parse():
    assert not verify_body_hmac(secret="", payload=b"{}", signature="abc")
    body = b'{"ok":true}'
    assert verify_body_hmac(secret="k", payload=body, signature=_signed("k", body))
    assert not verify_body_hmac(secret="k", payload=body, signature="nope")
    postmark = parse_postmark(
        {
            "From": "Ada <ada@example.com>",
            "To": "u.tok@news.example",
            "Subject": "Hello",
            "HtmlBody": "<p>Hi</p>",
            "TextBody": "",
            "MessageID": "m1",
            "Headers": [{"Name": "List-Unsubscribe", "Value": "<mailto:bye@example.com>"}],
        }
    )
    assert postmark.list_unsubscribe == "<mailto:bye@example.com>"
    assert recipient_token(postmark.recipient) == "tok"
    resend = parse_resend(
        {
            "data": {
                "from": "a@b.c",
                "to": ["u.tok@news.example"],
                "subject": "S",
                "text": "body",
                "email_id": "e1",
            }
        }
    )
    assert resend.message_id == "e1"
    cloud = parse_cloudflare(
        {
            "from": "a@b.c",
            "to": "reader+tok@news.example",
            "subject": "S",
            "html": "<p>Hi</p>",
            "message_id": "c1",
        }
    )
    assert recipient_token(cloud.recipient) == "tok"


def test_fifteen_newsletter_shapes_strip_pixels_and_unwrap():
    shapes = []
    for index, label in enumerate(
        [
            "substack",
            "beehiiv",
            "ghost",
            "mailchimp",
            "buttondown",
            "tinyletter",
            "convertkit",
            "revue",
            "wordpress",
            "medium",
            "plain",
            "confirm",
            "resend-copy",
            "digest",
            "announcement",
        ]
    ):
        confirm = (
            "Please confirm your subscription." if label == "confirm" else f"{label} issue {index}."
        )
        raw = (
            f"From: {label} <news@{label}.example>\r\n"
            f"To: u.token{index}@news.example\r\n"
            f"Subject: {label} {index}\r\n"
            f"Message-ID: <id-{index}@example>\r\n"
            "List-Unsubscribe: <mailto:bye@example.com>\r\n"
            "MIME-Version: 1.0\r\n"
            'Content-Type: text/html; charset="utf-8"\r\n'
            "\r\n"
            f'<html><body><img src="https://1.1.1.1/track/pixel.gif" width="1" height="1">'
            f'<a href="https://1.1.1.1/click?url=https%3A%2F%2F1.0.0.1%2Fstory">view in browser</a>'
            f"<p>{confirm}</p></body></html>"
        )
        shapes.append(parse_rfc822(raw))
    assert len(shapes) == 15
    parsed = shapes[0]
    assert "pixel" not in parsed.html
    assert parsed.view_in_browser == "https://1.0.0.1/story"
    assert parsed.list_unsubscribe
    assert shapes[11].is_confirmation
    assert not shapes[0].is_confirmation
    assert len({item.dedupe_key for item in shapes}) == 15
    assert unwrap_link("https://1.1.1.1/click?url=http://127.0.0.1/secret").startswith("https://")


def test_imap_batch_reads_rfc822():
    raw = (
        "From: Ada <ada@example.com>\r\nTo: u.abc@news.example\r\nSubject: Hello\r\n"
        "Message-ID: <abc@example>\r\nContent-Type: text/plain\r\n\r\nBody text\r\n"
    )
    batch = parse_imap_batch([raw.encode()])
    assert batch[0].text == "Body text"
    assert recipient_token(batch[0].recipient) == "abc"


@pytest.mark.asyncio
async def test_forward_creates_one_source_per_sender(db_session):
    from sqlalchemy import select

    from app.models.source import Source
    from app.models.user import User
    from app.services.ingestion.newsletter import ensure_newsletter_source

    user = User(email="reader@example.com", hashed_password="x", newsletter_token="tok")
    db_session.add(user)
    await db_session.flush()
    await ensure_newsletter_source(db_session, user.id, "Ada <ada@example.com>")
    await ensure_newsletter_source(db_session, user.id, "Ada <ada@example.com>")
    await db_session.flush()
    rows = (
        (await db_session.execute(select(Source).where(Source.user_id == user.id))).scalars().all()
    )
    assert len(rows) == 1
    assert rows[0].source_type == "newsletter"


@pytest.mark.asyncio
async def test_provider_endpoint_rejects_a_bad_signature(client, monkeypatch):
    from app.api import newsletter as newsletter_api

    monkeypatch.setattr(newsletter_api.settings, "app_env", "production")
    monkeypatch.setattr(newsletter_api.settings, "postmark_webhook_secret", "secret")
    response = await client.post(
        "/api/v1/newsletter/inbound/postmark",
        content=json.dumps({"From": "a", "To": "b", "Subject": "s", "TextBody": "hi"}),
        headers={"content-type": "application/json", "x-webhook-signature": "deadbeef"},
    )
    assert response.status_code == 401
