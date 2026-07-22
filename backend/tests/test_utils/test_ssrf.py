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
