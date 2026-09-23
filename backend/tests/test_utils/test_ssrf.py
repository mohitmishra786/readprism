"""Tests for SSRF protection (audit 06-2).

These never touch real DNS: IP literals resolve without lookups, and hostname
cases inject a fake resolver.
"""

from __future__ import annotations

import pytest

from app.utils import ssrf
from app.utils.ssrf import UnsafeURLError, is_public_url, validate_public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # AWS/GCP metadata (link-local)
        "http://127.0.0.1/admin",  # loopback
        "http://localhost:8000/",  # loopback hostname
        "http://10.0.0.5/internal",  # private
        "http://192.168.1.1/",  # private
        "http://172.16.0.1/",  # private
        "http://[::1]/",  # IPv6 loopback
        "http://0.0.0.0/",  # unspecified
        "http://metadata.google.internal/",  # GCP metadata hostname
        "ftp://example.com/file",  # disallowed scheme
        "file:///etc/passwd",  # disallowed scheme
        "http://100.64.0.1/",  # CGNAT (non-global)
    ],
)
def test_rejects_unsafe_urls(url):
    with pytest.raises(UnsafeURLError):
        validate_public_url(url)
    assert is_public_url(url) is False


def test_allows_public_ip_literal():
    # 1.1.1.1 is a public, globally-routable address; no DNS needed.
    validate_public_url("https://1.1.1.1/")
    assert is_public_url("https://1.1.1.1/") is True


def test_hostname_resolving_to_public_is_allowed():
    validate_public_url("https://feeds.example.com/rss", resolver=lambda h: ["93.184.216.34"])


def test_hostname_resolving_to_private_is_blocked():
    with pytest.raises(UnsafeURLError):
        validate_public_url("https://evil.example.com/", resolver=lambda h: ["10.1.2.3"])


def test_mixed_resolution_blocks_if_any_private():
    # DNS-rebinding style: one public + one private answer must be rejected.
    with pytest.raises(UnsafeURLError):
        validate_public_url(
            "https://evil.example.com/",
            resolver=lambda h: ["93.184.216.34", "127.0.0.1"],
        )


def test_ipv4_mapped_ipv6_loopback_blocked():
    with pytest.raises(UnsafeURLError):
        validate_public_url("http://[::ffff:127.0.0.1]/")


def test_disabled_toggle_is_noop(monkeypatch):
    monkeypatch.setattr(ssrf.settings, "ssrf_protection_enabled", False)
    # Would normally be blocked; disabled => allowed.
    validate_public_url("http://169.254.169.254/latest/meta-data/")


def test_rejects_credentials_in_url():
    with pytest.raises(UnsafeURLError):
        validate_public_url("https://user:secret@1.1.1.1/feed")


def test_rejects_decimal_loopback():
    # 2130706433 == 127.0.0.1
    with pytest.raises(UnsafeURLError):
        validate_public_url("http://2130706433/")


@pytest.mark.asyncio
async def test_redirect_to_private_is_blocked():
    import httpx

    hits = {"private": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "127.0.0.1":
            hits["private"] += 1
            return httpx.Response(200, text="secret")
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})

    with pytest.raises(UnsafeURLError):
        await ssrf.safe_fetch(
            "https://feeds.example.com/start",
            transport=httpx.MockTransport(handler),
            resolver=lambda host: ["93.184.216.34"],
        )
    assert hits["private"] == 0


@pytest.mark.asyncio
async def test_gzip_body_is_returned_without_a_second_decode():
    import gzip

    import httpx

    raw = b"<rss><channel><title>Feed</title></channel></rss>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip"},
            content=gzip.compress(raw),
        )

    resp = await ssrf.safe_fetch("https://1.1.1.1/feed.xml", transport=httpx.MockTransport(handler))
    assert b"<rss>" in resp.content
    assert "content-encoding" not in {k.lower() for k in resp.headers}


@pytest.mark.asyncio
async def test_body_over_cap_is_rejected():
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 50)

    with pytest.raises(UnsafeURLError, match="exceeded"):
        await ssrf.safe_fetch(
            "https://1.1.1.1/big",
            max_bytes=20,
            transport=httpx.MockTransport(handler),
        )
