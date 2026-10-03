"""Podcast transcripts (EC-08).

Use the feed description plus the Podcast 2.0 `<podcast:transcript>` link
(stored by IN-05) as the item body so episodes embed and rank. Fetched via
safe_fetch (SSRF-checked); plain text, WebVTT and SRT accepted. No YouTube
caption scraping (policy); local Whisper stays future opt-in work.
"""

from __future__ import annotations

import re

from app.utils.logging import get_logger
from app.utils.ssrf import safe_fetch

logger = get_logger(__name__)

TIMESTAMP = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?([.,]\d{1,3})?$")
SRT_RANGE = re.compile(r"^\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}\s*-->\s*\d{1,2}:\d{2}:\d{2}")
VTT_HEADER = re.compile(r"^(WEBVTT|NOTE|STYLE|REGION)\b")
TAG = re.compile(r"<[^>]+>")


def _is_furniture(line: str) -> bool:
    return bool(VTT_HEADER.match(line) or TIMESTAMP.match(line) or SRT_RANGE.match(line))


def clean_transcript(raw: str) -> str:
    """Strip WebVTT/SRT furniture (headers, cue numbers, timestamps, tags)."""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    kept: list[str] = []
    for index, line in enumerate(lines):
        if _is_furniture(line):
            continue
        # A bare number directly before a timestamp/range is a cue counter.
        if line.isdigit():
            nxt = lines[index + 1] if index + 1 < len(lines) else ""
            if _is_furniture(nxt):
                continue
        kept.append(TAG.sub("", line))
    text = " ".join(kept)
    return re.sub(r"\s+", " ", text).strip()


async def fetch_transcript_text(url: str) -> str | None:
    """Fetch and clean a transcript; None on any failure (non-fatal)."""
    try:
        resp = await safe_fetch(url, method="GET", max_bytes=1_000_000)
        if resp.status_code >= 400:
            return None
        body = resp.content.decode("utf-8", errors="replace")
        cleaned = clean_transcript(body)
        return cleaned or None
    except Exception as e:
        logger.info(f"Transcript fetch failed for {url}: {e}")
        return None
