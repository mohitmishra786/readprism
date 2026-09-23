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


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse an IP literal, including decimal and hex forms of an IPv4 address."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    if host.isdigit():
        try:
            return ipaddress.ip_address(int(host))
        except ValueError:
            return None
    if host.lower().startswith("0x"):
        try:
            return ipaddress.ip_address(int(host, 16))
        except ValueError:
            return None
    return None


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
    if parsed.username or parsed.password:
        raise UnsafeURLError("credentials in URLs are not allowed")

    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no host")
    host = host.rstrip(".")

    lowered = host.lower()
    if lowered in _BLOCKED_HOSTNAMES or lowered.endswith(".localhost"):
        raise UnsafeURLError(f"host {host!r} is not permitted")

    # If the host is already an IP literal, check it directly (no DNS).
    literal_ip = _literal_ip(lowered)
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


# Cap a single fetched body. Feeds and articles above this are rejected rather
# than buffered without limit.
DEFAULT_MAX_BYTES = 5_000_000
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_REDIRECTS = 5


async def _read_capped(resp: httpx.Response, max_bytes: int) -> bytes:
    declared = resp.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise UnsafeURLError(f"response exceeded {max_bytes} bytes")
    buf = bytearray()
    async for chunk in resp.aiter_bytes():
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise UnsafeURLError(f"response exceeded {max_bytes} bytes")
    return bytes(buf)


async def safe_fetch(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    resolver: Callable[[str], Iterable[str]] = _default_resolver,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.Response:
    """Fetch `url`, validating every hop before connecting.

    This is the only function that should open a connection to a user-supplied
    URL. It enforces the scheme allowlist, blocks credentials in the URL,
    re-checks DNS (or IP literals) on every redirect, caps the body, and applies
    a timeout. `resolver` and `transport` are injectable for tests.
    """
    current = url
    client = httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(timeout),
        follow_redirects=False,
    )
    try:
        for _ in range(max_redirects + 1):
            validate_public_url(current, resolver=resolver)
            async with client.stream(method, current, headers=headers) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    current = urljoin(str(resp.url), resp.headers["location"])
                    continue
                body = await _read_capped(resp, max_bytes)
                # aiter_bytes already decoded Content-Encoding. Copying that
                # header onto the decoded body makes httpx decode it again.
                forwarded = [
                    (key, value)
                    for key, value in resp.headers.multi_items()
                    if key.lower()
                    not in {"content-encoding", "content-length", "transfer-encoding"}
                ]
                return httpx.Response(
                    status_code=resp.status_code,
                    headers=forwarded,
                    content=body,
                    request=resp.request,
                )
        raise UnsafeURLError(f"too many redirects fetching {url!r}")
    finally:
        await client.aclose()


async def safe_get(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    **kwargs,
) -> httpx.Response:
    """GET `url` through `safe_fetch`.

    `client` is accepted for older call sites and ignored: the shared fetcher
    owns the connection, the timeout, and the redirect policy.
    """
    del client
    timeout = float(kwargs.pop("timeout", DEFAULT_TIMEOUT_SECONDS))
    headers = kwargs.pop("headers", None)
    max_bytes = int(kwargs.pop("max_bytes", DEFAULT_MAX_BYTES))
    resolver = kwargs.pop("resolver", _default_resolver)
    transport = kwargs.pop("transport", None)
    if kwargs:
        raise TypeError(f"unexpected safe_get arguments: {sorted(kwargs)}")
    return await safe_fetch(
        url,
        headers=headers,
        timeout=timeout,
        max_redirects=max_redirects,
        max_bytes=max_bytes,
        resolver=resolver,
        transport=transport,
    )
