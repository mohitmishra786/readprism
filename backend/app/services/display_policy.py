"""What the reader may display (#177).

Hosted policy: show what the publisher syndicated in its feed, plus a short
summary (labelled when it is AI-written) and a link to the original. Text
Weirling extracted from the page itself (trafilatura, readability, a
rendered page) is used for ranking and summaries only and is not shown,
except to the person who saved it. Self-hosted instances read their own
fetches and show everything; `READER_FULL_TEXT` overrides either default.
"""

from __future__ import annotations

from app.config import get_settings

FEED_METHODS = frozenset({"feed"})


def policy() -> str:
    mode = (get_settings().reader_full_text or "auto").strip().lower()
    if mode in ("all", "feed_only"):
        return mode
    return "feed_only" if get_settings().deployment_mode == "hosted" else "all"


def may_display_full_text(item, viewer_id) -> bool:
    if policy() == "all":
        return True
    if item.owner_user_id is not None and item.owner_user_id == viewer_id:
        return True  # their own save or newsletter
    return (item.extraction_method or "") in FEED_METHODS
