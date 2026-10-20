"""First-party product metrics and the North Star dashboard (D-20, #131)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models.content import ContentItem
from app.models.digest import Digest, DigestItem
from app.models.product_event import ProductEvent, ProductMetricDaily
from app.models.user import User
from app.services import product_metrics as pm

NOW = datetime.now(UTC)


@pytest.fixture
def hosted(monkeypatch):
    s = get_settings()
    for key, value in {
        "deployment_mode": "hosted",
        "registration_mode": "open",
        "email_verification": "off",
        "billing_trial_days": 30,
        "product_metrics": "auto",
    }.items():
        monkeypatch.setattr(s, key, value)
    from app.services import entitlements

    if entitlements.settings is not s:
        monkeypatch.setattr(entitlements.settings, "deployment_mode", "hosted")
        monkeypatch.setattr(entitlements.settings, "billing_trial_days", 30)
    return s


# ------------------------------------------------------------ pure parts


def test_enabled_by_mode(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "product_metrics", "auto")
    monkeypatch.setattr(s, "deployment_mode", "selfhost")
    assert not pm.enabled()  # self-hosted installs record nothing by default
    monkeypatch.setattr(s, "deployment_mode", "hosted")
    assert pm.enabled()
    monkeypatch.setattr(s, "product_metrics", "off")
    assert not pm.enabled()
    monkeypatch.setattr(s, "deployment_mode", "selfhost")
    monkeypatch.setattr(s, "product_metrics", "on")
    assert pm.enabled()


def _after(**kw):
    base = {"opened_at": None, "read_completion_pct": None, "explicit_rating": None, "saved": False}
    return SimpleNamespace(**{**base, **kw})


def test_only_real_transitions_are_events():
    opened = NOW
    assert pm.interaction_events(None, _after(opened_at=opened)) == [("item_opened", {})]
    before = {"opened_at": opened, "completion": 0.5, "rating": None, "saved": False}
    assert pm.interaction_events(before, _after(opened_at=opened, read_completion_pct=0.8)) == [
        ("item_finished", {})
    ]
    # Re-sent telemetry after finishing isn't a second finish.
    again = {"opened_at": opened, "completion": 0.8, "rating": 1, "saved": True}
    assert (
        pm.interaction_events(
            again,
            _after(opened_at=opened, read_completion_pct=0.9, explicit_rating=1, saved=True),
        )
        == []
    )
    assert pm.interaction_events(again, _after(opened_at=opened, explicit_rating=-1)) == [
        ("rating", {"value": -1})
    ]


# ------------------------------------------------------------ end to end


async def _events(db_session, event=None, user_id=None) -> list[ProductEvent]:
    db_session.expire_all()
    q = select(ProductEvent)
    if event:
        q = q.where(ProductEvent.event == event)
    if user_id:
        q = q.where(ProductEvent.user_id == user_id)
    return list((await db_session.execute(q)).scalars())


async def _signup(client, db_session):
    email = f"pm{uuid.uuid4().hex[:8]}@example.com"
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "TestPass123!", "accept_terms": True},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    return uuid.UUID(me["id"]), headers


async def _digest_with_items(db_session, user_id, n=5) -> Digest:
    digest = Digest(user_id=user_id, total_items=n)
    db_session.add(digest)
    await db_session.flush()
    for i in range(n):
        item = ContentItem(url=f"https://x.example/{uuid.uuid4().hex}", title=f"t{i}")
        db_session.add(item)
        await db_session.flush()
        db_session.add(
            DigestItem(
                digest_id=digest.id,
                content_item_id=item.id,
                position=i,
                section="lead",
                prs_score=0.5,
            )
        )
    await db_session.commit()
    return digest


@pytest.mark.asyncio
async def test_signup_and_reading_events_and_digest_opened_flag(client, db_session, hosted):
    uid, headers = await _signup(client, db_session)
    assert len(await _events(db_session, "signup", uid)) == 1

    digest = await _digest_with_items(db_session, uid)
    digest_id = digest.id
    item_id = (
        await db_session.execute(
            select(DigestItem.content_item_id).where(DigestItem.digest_id == digest_id).limit(1)
        )
    ).scalar_one()

    body = (await client.get(f"/api/v1/digest/{digest_id}", headers=headers)).json()
    assert body["ask_top5"] is True
    db_session.expire_all()
    assert (await db_session.get(Digest, digest_id)).opened is True  # was never set before
    await client.get(f"/api/v1/digest/{digest_id}", headers=headers)
    assert len(await _events(db_session, "digest_opened", uid)) == 1  # once per digest

    post = {"content_item_id": str(item_id), "read_completion_pct": 0.8, "explicit_rating": 1}
    with patch(
        "app.workers.tasks.update_interest_graph.update_interest_graph_for_interaction.delay"
    ):
        await client.post("/api/v1/feedback/interaction", json=post, headers=headers)
        await client.post("/api/v1/feedback/interaction", json=post, headers=headers)
    kinds = sorted(e.event for e in await _events(db_session, user_id=uid))
    assert kinds.count("item_finished") == 1 and kinds.count("rating") == 1
    assert "item_opened" in kinds


@pytest.mark.asyncio
async def test_email_click_opens_the_digest(db_session, hosted):
    from app.api.digest import _record_email_action

    user = User(email=f"em{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    digest = await _digest_with_items(db_session, user.id, n=2)
    item_id = (
        await db_session.execute(
            select(DigestItem.content_item_id).where(DigestItem.digest_id == digest.id).limit(1)
        )
    ).scalar_one()
    uid, digest_id = user.id, digest.id
    await _record_email_action(user, item_id, "open", db_session)
    await db_session.commit()
    assert (await db_session.get(Digest, digest_id, populate_existing=True)).opened is True
    opened = await _events(db_session, "digest_opened", uid)
    assert opened[0].props == {"via": "email"}


@pytest.mark.asyncio
async def test_top5_once_per_digest(client, db_session, hosted):
    uid, headers = await _signup(client, db_session)
    digest = await _digest_with_items(db_session, uid)
    url = f"/api/v1/digest/{digest.id}/top5"
    assert (await client.post(url, json={"wanted": 4}, headers=headers)).json()["status"] == (
        "recorded"
    )
    assert (await client.post(url, json={"wanted": 1}, headers=headers)).json()["status"] == (
        "already_answered"
    )
    assert (await client.post(url, json={"wanted": 9}, headers=headers)).status_code == 422
    assert (await client.get(f"/api/v1/digest/{digest.id}", headers=headers)).json()[
        "ask_top5"
    ] is False


@pytest.mark.asyncio
async def test_billing_conversion_and_cancel(db_session, hosted):
    from app.services.billing import _track_plan_change

    user = User(email=f"bc{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    user.trial_ends_at = NOW + timedelta(days=3)
    db_session.add(user)
    await db_session.flush()
    user.tier, user.plan_expires_at, user.billing_status = (
        "reader",
        NOW + timedelta(days=30),
        "active",
    )
    await _track_plan_change(db_session, user, "trial", None, NOW)
    user.billing_status = "cancelled"
    await _track_plan_change(db_session, user, "reader", "active", NOW)
    uid = user.id
    await db_session.commit()
    converted = await _events(db_session, "trial_converted", uid)
    assert converted[0].props == {"plan": "reader", "previous": "trial"}
    assert len(await _events(db_session, "cancel", uid)) == 1


@pytest.mark.asyncio
async def test_selfhost_records_nothing(client, db_session, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "deployment_mode", "selfhost")
    monkeypatch.setattr(s, "product_metrics", "auto")
    monkeypatch.setattr(s, "registration_mode", "open")
    uid, _ = await _signup(client, db_session)
    assert await _events(db_session, user_id=uid) == []


@pytest.mark.asyncio
async def test_north_star_retention_rollup_and_dashboard(client, db_session, hosted):
    reader = User(email=f"ns{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    db_session.add(reader)
    await db_session.flush()

    def ev(event, days_ago):
        return ProductEvent(
            user_id=reader.id, event=event, props={}, created_at=NOW - timedelta(days=days_ago)
        )

    db_session.add_all(
        [ev("digest_opened", d) for d in (1, 2, 3)]
        + [ev("item_finished", d) for d in (1, 2, 4)]
        + [ev("signup", 15), ev("digest_opened", 6)]  # opened on day 9 after signing up
    )
    await db_session.commit()

    assert await pm.weekly_satisfied_readers(db_session, NOW) == 1
    assert await pm.retention(db_session, NOW, 7) == 1.0

    values = await pm.rollup(db_session, (NOW - timedelta(days=1)).date())
    await db_session.commit()
    assert values["events.digest_opened"] >= 1
    stored = (
        await db_session.execute(select(func.count()).select_from(ProductMetricDaily))
    ).scalar_one()
    assert stored == len(values)


@pytest.mark.asyncio
async def test_dashboard_is_owner_only(client, db_session, hosted):
    owner_id, owner = await _signup(client, db_session)
    _, other = await _signup(client, db_session)
    with patch(
        "app.services.instance_health.is_instance_owner",
        AsyncMock(side_effect=lambda session, user: user.id == owner_id),
    ):
        assert (await client.get("/api/v1/metrics/product", headers=other)).status_code == 403
        body = (await client.get("/api/v1/metrics/product", headers=owner)).json()
    assert body["enabled"] is True and "weekly_satisfied_readers" in body["now"]
    assert body["targets"]["retention_d7"] == ">= 0.60"


@pytest.mark.asyncio
async def test_events_are_exported_and_deleted_with_the_account(client, db_session, hosted):
    uid, headers = await _signup(client, db_session)
    export = (await client.get("/api/v1/account/export", headers=headers)).json()
    assert [e["event"] for e in export["product_events"]] == ["signup"]
    with patch("app.utils.email.send_email", AsyncMock(return_value=True)):
        assert (await client.delete("/api/v1/account", headers=headers)).status_code == 204
    assert await _events(db_session, user_id=uid) == []
