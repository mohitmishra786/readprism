from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User
from app.services.account.gdpr import export_user_data


@pytest.mark.asyncio
async def test_hosted_registration_requires_terms_consent(client: AsyncClient, monkeypatch):
    import app.api.auth as auth_mod

    monkeypatch.setattr(get_settings(), "deployment_mode", "hosted")
    monkeypatch.setattr(auth_mod.settings, "deployment_mode", "hosted")

    # Hosted registration without accept_terms fails with 422
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "terms_reject@example.com",
            "password": "Password123!",
            "accept_terms": False,
        },
    )
    assert resp.status_code == 422
    assert "Terms" in resp.json()["detail"]

    # Hosted registration with accept_terms succeeds
    resp_ok = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "terms_accept@example.com",
            "password": "Password123!",
            "accept_terms": True,
        },
    )
    assert resp_ok.status_code == 201


@pytest.mark.asyncio
async def test_selfhost_registration_does_not_require_terms_consent(
    client: AsyncClient, monkeypatch
):
    import app.api.auth as auth_mod

    monkeypatch.setattr(get_settings(), "deployment_mode", "selfhost")
    monkeypatch.setattr(auth_mod.settings, "deployment_mode", "selfhost")
    monkeypatch.setattr(get_settings(), "registration_mode", "open")

    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "selfhost_user@example.com",
            "password": "Password123!",
        },
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_registration_state_reports_hosted_mode(client: AsyncClient, monkeypatch):
    import app.api.auth as auth_mod

    monkeypatch.setattr(get_settings(), "deployment_mode", "hosted")
    monkeypatch.setattr(auth_mod.settings, "deployment_mode", "hosted")

    resp = await client.get("/api/v1/auth/registration")
    assert resp.status_code == 200
    assert resp.json()["hosted"] is True

    monkeypatch.setattr(get_settings(), "deployment_mode", "selfhost")
    monkeypatch.setattr(auth_mod.settings, "deployment_mode", "selfhost")

    resp2 = await client.get("/api/v1/auth/registration")
    assert resp2.status_code == 200
    assert resp2.json()["hosted"] is False


@pytest.mark.asyncio
async def test_consent_stored_and_exported_in_gdpr(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    import app.api.auth as auth_mod

    monkeypatch.setattr(get_settings(), "deployment_mode", "hosted")
    monkeypatch.setattr(auth_mod.settings, "deployment_mode", "hosted")
    monkeypatch.setattr(get_settings(), "terms_version", "2026-07-21")
    monkeypatch.setattr(auth_mod.settings, "terms_version", "2026-07-21")

    email = "gdpr_terms@example.com"
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "accept_terms": True,
        },
    )
    assert resp.status_code == 201

    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    assert user.terms_accepted_at is not None
    assert user.terms_version == "2026-07-21"

    exported = await export_user_data(db_session, user)
    profile = exported["profile"]
    assert "terms_accepted_at" in profile
    assert profile["terms_accepted_at"] is not None
    assert profile["terms_version"] == "2026-07-21"


@pytest.mark.asyncio
async def test_magic_link_signup_on_hosted_needs_consent(client, db_session, monkeypatch):
    """#181: the magic link doubles as sign-up, so it must not skip consent."""
    from unittest.mock import AsyncMock, patch

    s = get_settings()
    monkeypatch.setattr(s, "deployment_mode", "hosted")
    monkeypatch.setattr(s, "registration_mode", "open")
    monkeypatch.setattr(s, "email_verification", "off")

    async def user_for(email):
        db_session.expire_all()
        return (
            await db_session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

    with patch("app.utils.email.send_email", AsyncMock(return_value=True)):
        no = await client.post(
            "/api/v1/auth/magic-link/request", json={"email": "ml-no@example.com"}
        )
        yes = await client.post(
            "/api/v1/auth/magic-link/request",
            json={"email": "ml-yes@example.com", "accept_terms": True},
        )
    assert no.status_code == yes.status_code == 202  # same answer: not enumerating
    assert await user_for("ml-no@example.com") is None
    created = await user_for("ml-yes@example.com")
    assert created is not None and created.terms_accepted_at is not None
    assert created.terms_version == s.terms_version
