"""Aggregate metrics: North Star, funnel, cohort retention, token gating (17)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.api import metrics as metrics_api
from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import Digest
from app.models.user import User


@pytest.mark.asyncio
async def test_metrics_token_gate_in_production(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(metrics_api.settings, "metrics_token", "secret")
    monkeypatch.setattr(metrics_api.settings, "app_env", "production")
    # No token header -> 401.
    resp = await client.get("/api/v1/metrics/north-star")
    assert resp.status_code == 401
    # Correct token -> 200.
    ok = await client.get("/api/v1/metrics/north-star", headers={"X-Metrics-Token": "secret"})
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_north_star_suggestion_read_rate(client: AsyncClient, db_session, monkeypatch):
    monkeypatch.setattr(metrics_api.settings, "metrics_token", "")
    monkeypatch.setattr(metrics_api.settings, "app_env", "development")

    user = User(email="m@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    c1 = ContentItem(url="https://x/1", title="a")
    c2 = ContentItem(url="https://x/2", title="b")
    db_session.add_all([c1, c2])
    await db_session.flush()
    now = datetime.now(UTC)
    # One suggested opened read, one non-suggested opened read -> rate 0.5.
    db_session.add(
        UserContentInteraction(
            user_id=user.id, content_item_id=c1.id, opened_at=now, was_suggested=True
        )
    )
    db_session.add(
        UserContentInteraction(
            user_id=user.id, content_item_id=c2.id, opened_at=now, was_suggested=False
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/metrics/north-star")
    assert resp.status_code == 200
    body = resp.json()
    assert body["opened_reads"] == 2
    assert body["suggested_reads"] == 1
    assert body["suggestion_read_rate"] == 0.5


@pytest.mark.asyncio
async def test_cohort_retention_and_funnel(client: AsyncClient, db_session, monkeypatch):
    monkeypatch.setattr(metrics_api.settings, "metrics_token", "")
    monkeypatch.setattr(metrics_api.settings, "app_env", "development")

    user = User(email="r@example.com", hashed_password="x", onboarding_complete=True)
    db_session.add(user)
    await db_session.flush()
    # A digest opened 8 days after signup -> counts toward D1 and D7, not D30.
    signup = user.created_at if user.created_at.tzinfo else user.created_at.replace(tzinfo=UTC)
    db_session.add(Digest(user_id=user.id, opened=True, generated_at=signup + timedelta(days=8)))
    await db_session.commit()

    funnel = (await client.get("/api/v1/metrics/cold-start-funnel")).json()
    assert funnel["signed_up"] >= 1
    assert funnel["onboarded"] >= 1

    cohorts = (await client.get("/api/v1/metrics/cohort-retention")).json()
    assert isinstance(cohorts, list) and cohorts


@pytest.mark.asyncio
async def test_time_to_value(client: AsyncClient, db_session, monkeypatch):
    """CS-06: local-only signup->digest->read medians."""
    monkeypatch.setattr(metrics_api.settings, "metrics_token", "")
    monkeypatch.setattr(metrics_api.settings, "app_env", "development")

    from datetime import UTC, datetime, timedelta

    from app.models.content import ContentItem
    from app.models.digest import Digest
    from app.models.user import User

    t0 = datetime(2026, 10, 1, tzinfo=UTC)
    user = User(
        email="ttv@example.com",
        hashed_password="x",
        onboarding_complete=True,
        created_at=t0,
    )
    db_session.add(user)
    await db_session.flush()
    item = ContentItem(url="https://ttv.example/a", title="a", fetched_at=t0)
    db_session.add(item)
    await db_session.flush()
    from app.models.content import UserContentInteraction

    db_session.add(
        Digest(user_id=user.id, generated_at=t0 + timedelta(hours=2), delivery_method="in_app")
    )
    db_session.add(
        UserContentInteraction(
            user_id=user.id, content_item_id=item.id, opened_at=t0 + timedelta(hours=5)
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/metrics/time-to-value")
    assert resp.status_code == 200
    body = resp.json()
    assert body["median_hours_signup_to_first_digest"] == 2.0
    assert body["median_hours_first_digest_to_first_read"] == 3.0
