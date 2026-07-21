"""SSRF (Server-Side Request Forgery) protection for server-side URL fetches.

Any URL that originates from user input (a source URL, a feed to autodiscover,
a page to scrape) is fetched by *our* server. Without guarding, an attacker can
add `http://169.254.169.254/latest/meta-data/` (cloud metadata) or an internal
host as a "source" and exfiltrate credentials or reach internal services.

This module validates that a URL's host resolves only to public, routable IPs
and that redirects can't smuggle the request onto a private target. It is a hard
constraint on the scraping/ingestion path (audit 06-2, 08); it can be disabled
per-deployment for single-tenant homelab use via `ssrf_protection_enabled`.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urljoin, urlparse

import httpx

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_ALLOWED_SCHEMES = {"http", "https"}

# Hostnames that never resolve to something we should reach, independent of DNS.
_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",  # GCP metadata
    "metadata",
}


class UnsafeURLError(ValueError):
    """Raised when a URL fails SSRF validation (private target / bad scheme)."""


def _blocked_ip_reason(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Return a human reason if `ip` must not be fetched, else None."""
    # IPv4-mapped IPv6 (::ffff:a.b.c.d) — unwrap and re-check the embedded v4.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _blocked_ip_reason(ip.ipv4_mapped)
    if ip.is_loopback:
        return "loopback"
    if ip.is_private:
        return "private"
    if ip.is_link_local:
        return "link-local"  # includes 169.254.0.0/16 cloud-metadata range
    if ip.is_reserved:
        return "reserved"
    if ip.is_multicast:
        return "multicast"
    if ip.is_unspecified:
        return "unspecified"
    # Catch-all for anything not globally routable (e.g. 100.64/10 CGNAT, 0/8).
    if not ip.is_global:
        return "non-global"
    return None


def _default_resolver(host: str) -> list[str]:
    """Resolve `host` to the set of IP strings it points at (A + AAAA)."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return list({info[4][0] for info in infos})


def validate_public_url(
    url: str,
    *,
    resolver: Callable[[str], Iterable[str]] = _default_resolver,
) -> None:
    """Raise `UnsafeURLError` unless `url` is an http(s) URL whose host resolves
    exclusively to public, globally-routable IP addresses.

    `resolver` is injectable so tests can exercise host validation without real
    DNS. When `ssrf_protection_enabled` is False this is a no-op.
    """
    if not settings.ssrf_protection_enabled:
        return

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"scheme {scheme!r} not allowed (only http/https)")

    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no host")

    lowered = host.lower()
    if lowered in _BLOCKED_HOSTNAMES or lowered.endswith(".localhost"):
        raise UnsafeURLError(f"host {host!r} is not permitted")

    # If the host is already an IP literal, check it directly (no DNS).
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        reason = _blocked_ip_reason(literal_ip)
        if reason:
            raise UnsafeURLError(f"IP {host} is {reason}")
        return

    # Hostname: resolve and ensure *every* answer is public (guards round-robin
    # and DNS setups that return one public + one private record).
    try:
        addresses = list(resolver(host))
    except OSError as e:
        raise UnsafeURLError(f"could not resolve host {host!r}: {e}") from e
    if not addresses:
        raise UnsafeURLError(f"host {host!r} did not resolve")
    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        reason = _blocked_ip_reason(ip)
        if reason:
            raise UnsafeURLError(f"host {host!r} resolves to {reason} address {addr}")


def is_public_url(url: str) -> bool:
    """Boolean convenience wrapper around `validate_public_url`."""
    try:
        validate_public_url(url)
        return True
    except UnsafeURLError:
        return False


async def safe_get(
    url: str,
    *,
    client: httpx.AsyncClient,
    max_redirects: int = 5,
    **kwargs,
) -> httpx.Response:
    """GET `url` with SSRF validation on the initial URL *and every redirect hop*.

    Redirects are followed manually (rather than by httpx) so that each `Location`
    is validated before we connect to it — closing the "public URL 302s to an
    internal host" bypass. The provided `client` must have redirect-following
    disabled (we pass `follow_redirects=False` per request to be safe).
    """
    current = url
    for _ in range(max_redirects + 1):
        validate_public_url(current)
        resp = await client.get(current, follow_redirects=False, **kwargs)
        if resp.is_redirect and "location" in resp.headers:
            current = urljoin(current, resp.headers["location"])
            continue
        return resp
    raise UnsafeURLError(f"too many redirects fetching {url!r}")
