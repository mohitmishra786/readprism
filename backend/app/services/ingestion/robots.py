"""Scrape-mode policy: robots.txt, a domain kill switch, and a per-host gap.

A served robots file is honored. A clean 404 means allowed. A fetch error
fails closed unless ``robots_fail_open`` is set. The kill switch is a
comma-separated host list and does not depend on robots.txt.
"""

from __future__ import annotations

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def domain_denied(url: str, deny_list: str) -> bool:
    host = host_of(url)
    if not host:
        return True
    denied = {
        item.strip().lower().removeprefix("www.") for item in deny_list.split(",") if item.strip()
    }
    return any(host == name or host.endswith("." + name) for name in denied)


def robots_decision(status: str, text: str, url: str, *, fail_open: bool) -> bool:
    """status is ok, absent, or error. True means scraping is allowed."""
    if status == "absent":
        return True
    if status == "error":
        return fail_open
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    return parser.can_fetch("*", url)


def host_wait(last_fetch_at: float | None, now: float, gap_seconds: float = 1.0) -> float:
    """Seconds to wait so two scrapes of one host stay ``gap_seconds`` apart."""
    if last_fetch_at is None:
        return 0.0
    return max(0.0, gap_seconds - (now - last_fetch_at))
