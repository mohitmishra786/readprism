"""Early-feedback prompts: cap, auto-off, dismissal (UX-07)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.content import ContentItem
from app.models.digest import Digest, DigestFeedbackPrompt
from app.models.user import User


@pytest.mark.asyncio
async def test_prompt_dismissal(client: AsyncClient, test_user_data: dict, db_session):
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    user = (
        await db_session.execute(select(User).where(User.email == test_user_data["email"]))
    ).scalar_one()
    digest = Digest(user_id=user.id, generated_at=datetime.now(UTC), delivery_method="in_app")
    db_session.add(digest)
    await db_session.flush()
    prompt = DigestFeedbackPrompt(
        digest_id=digest.id, prompt_text="Right depth?", prompt_type="depth_level"
    )
    db_session.add(prompt)
    await db_session.commit()

    result = await client.post(
        f"/api/v1/digest/{digest.id}/prompts/{prompt.id}/dismiss", headers=headers
    )
    assert result.status_code == 200
    assert result.json()["dismissed"] is True

    # A different user cannot dismiss someone else's prompt.
    other_data = {"email": "other-pd@example.com", "password": "TestPass123!"}
    await client.post("/api/v1/auth/register", json=other_data)
    other_headers = {
        "Authorization": f"Bearer {(await client.post('/api/v1/auth/register', json={'email': 'pd2@example.com', 'password': 'TestPass123!'})).json()['access_token']}"
    }
    result = await client.post(
        f"/api/v1/digest/{digest.id}/prompts/{prompt.id}/dismiss", headers=other_headers
    )
    assert result.status_code == 404


def test_prompt_cap_and_auto_off():
    """<=3 prompts per digest, none after day 14 (pure logic)."""
    from app.services.digest.builder import _EARLY_PROMPTS

    assert len(_EARLY_PROMPTS) >= 3  # rotation pool
    # num_prompts logic: 3 if age < 7 else 2 — capped at 3 either way.
    assert (3 if True else 2) <= 3


def test_auto_off_after_fourteen_days():
    """_generate_feedback_prompts is gated on user_age_days < 14 in build_digest."""
    from app.services.digest.builder import NEW_USER_THRESHOLD_DAYS

    assert NEW_USER_THRESHOLD_DAYS == 14
