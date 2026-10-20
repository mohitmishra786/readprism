"""Tests for instance-wide takedown list (#183)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.source import Source
from app.models.user import User
from app.services.takedown import (
    add_blocked_entry,
    is_url_blocked,
    normalize_target,
    not_blocked_filter,
    remove_blocked_entry,
)


@pytest.mark.asyncio
async def test_normalize_target():
    # URL normalization
    assert (
        normalize_target("https://example.com/post?utm_source=twitter")
        == "https://example.com/post"
    )
    assert normalize_target("http://example.com/a/b/") == "http://example.com/a/b"

    # Host normalization
    assert normalize_target("example.com") == "example.com"
    assert normalize_target("www.example.com") == "example.com"
    assert normalize_target("https://example.com/") == "example.com"
    assert normalize_target("https://example.com") == "example.com"
    assert normalize_target("sub.domain.co.uk") == "sub.domain.co.uk"
    assert normalize_target("https://example.com/foo", is_host=True) == "example.com"


@pytest.mark.asyncio
async def test_add_and_remove_takedown(db_session):
    # Add URL
    entry = await add_blocked_entry(db_session, "https://example.com/blocked-1", "DMCA request")
    assert entry.url_key == "https://example.com/blocked-1"
    assert entry.reason == "DMCA request"

    assert await is_url_blocked(db_session, "https://example.com/blocked-1")
    assert await is_url_blocked(db_session, "https://example.com/blocked-1?utm_campaign=x")
    assert not await is_url_blocked(db_session, "https://example.com/other")

    # Add Host
    host_entry = await add_blocked_entry(db_session, "badsite.org", "Intermediary takedown")
    assert host_entry.url_key == "badsite.org"
    assert await is_url_blocked(db_session, "https://badsite.org/anything")
    assert await is_url_blocked(db_session, "https://sub.badsite.org/page")
    assert await is_url_blocked(db_session, "https://a.b.badsite.org/page")
    assert not await is_url_blocked(db_session, "https://notbadsite.org/page")

    # Remove
    removed = await remove_blocked_entry(db_session, "https://example.com/blocked-1")
    assert removed
    assert not await is_url_blocked(db_session, "https://example.com/blocked-1")

    # Still host blocked
    assert await is_url_blocked(db_session, "https://badsite.org/anything")
    assert await remove_blocked_entry(db_session, "badsite.org")
    assert not await is_url_blocked(db_session, "https://badsite.org/anything")


@pytest.mark.asyncio
async def test_takedown_cli_script(db_session):
    from unittest.mock import patch

    from scripts.takedown import run_takedown
    from tests.conftest import TestingSessionLocal

    # The script opens its own session: point it at the test database.
    with patch("app.database.AsyncSessionLocal", TestingSessionLocal):
        code = await run_takedown("https://example.com/cli-test", "Test CLI add", remove=False)
        assert code == 0
        assert await is_url_blocked(db_session, "https://example.com/cli-test")

        code = await run_takedown("https://example.com/cli-test", "", remove=True)
        assert code == 0
        assert not await is_url_blocked(db_session, "https://example.com/cli-test")
