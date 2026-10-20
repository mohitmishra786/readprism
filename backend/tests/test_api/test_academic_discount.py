"""Academic discount at checkout (#250)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.billing import academic_discount_for, academic_eligible


def _user(email, verified=True):
    return SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        email=email,
        email_verified_at=datetime(2026, 1, 1, tzinfo=UTC) if verified else None,
    )


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("ada@mit.edu", True),
        ("ada@cs.stanford.edu", True),
        ("ada@ox.ac.uk", True),
        ("ada@student.unimelb.edu.au", True),
        ("ada@iitb.ac.in", True),
        ("ada@edu.example.com", False),  # 'edu' must be the suffix, not a label inside
        ("ada@notmit-edu.com", False),
        ("ada@gmail.com", False),
    ],
)
def test_eligible_domains(email, expected):
    assert academic_eligible(_user(email)) is expected


def test_unverified_email_never_qualifies():
    assert academic_eligible(_user("ada@mit.edu", verified=False)) is False


def test_no_discount_configured_means_none(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "billing_academic_discount", "")
    assert academic_discount_for(_user("ada@mit.edu")) is None


@pytest.mark.asyncio
async def test_paddle_checkout_carries_the_discount(monkeypatch):
    from app.config import get_settings
    from app.services.billing import paddle

    s = get_settings()
    monkeypatch.setattr(s, "billing_academic_discount", "dsc_academic")
    monkeypatch.setattr(s, "billing_checkout_monthly", "pri_monthly")
    monkeypatch.setattr(s, "billing_api_key", "key")
    response = MagicMock()
    response.json.return_value = {"data": {"checkout": {"url": "https://pay.example/c"}}}
    post = AsyncMock(return_value=response)
    with patch("httpx.AsyncClient.post", post):
        assert await paddle.checkout_url(_user("ada@mit.edu"), "month") == "https://pay.example/c"
        assert post.await_args.kwargs["json"]["discount_id"] == "dsc_academic"
        await paddle.checkout_url(_user("ada@gmail.com"), "month")
        assert "discount_id" not in post.await_args.kwargs["json"]


@pytest.mark.asyncio
async def test_lemonsqueezy_checkout_carries_the_code(monkeypatch):
    from app.config import get_settings
    from app.services.billing import lemonsqueezy

    s = get_settings()
    monkeypatch.setattr(s, "billing_academic_discount", "ACADEMIC40")
    monkeypatch.setattr(s, "billing_checkout_monthly", "https://shop.example/checkout/buy/abc")
    url = await lemonsqueezy.checkout_url(_user("ada@ox.ac.uk"), "month")
    assert "checkout%5Bdiscount_code%5D=ACADEMIC40" in url
    assert "discount_code" not in await lemonsqueezy.checkout_url(_user("ada@gmail.com"), "month")


@pytest.mark.asyncio
async def test_billing_state_tells_the_reader(client, monkeypatch, db_session):
    import uuid

    from sqlalchemy import select

    from app.config import get_settings
    from app.models.user import User

    monkeypatch.setattr(get_settings(), "billing_academic_discount", "dsc_academic")
    email = f"r{uuid.uuid4().hex[:6]}@uni.edu"
    reg = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "TestPass123!"}
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    assert (await client.get("/api/v1/billing", headers=headers)).json()[
        "academic_discount"
    ] is False
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.email_verified_at = datetime.now(UTC)
    await db_session.commit()
    assert (await client.get("/api/v1/billing", headers=headers)).json()[
        "academic_discount"
    ] is True
