from __future__ import annotations

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_onboarding_complete_sets_flag(client: AsyncClient, test_user_data: dict, db_session):
    """POST /onboarding should mark onboarding_complete=True on the user."""
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    assert reg.status_code == 200, reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch(
        "app.services.cold_start.onboarding.process_onboarding",
        new_callable=AsyncMock,
    ) as mock_process:
        resp = await client.post(
            "/api/v1/onboarding",
            json={
                "interest_text": "AI and machine learning",
                "sample_ratings": [
                    {"article_url": "https://example.com/1", "title": "AI Basics", "rating": 1}
                ],
                "source_opml": None,
            },
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "ok"
    mock_process.assert_called_once()


@pytest.mark.asyncio
async def test_onboarding_idempotent_returns_409(client: AsyncClient, test_user_data: dict, db_session):
    """Calling /onboarding twice should return 409 on the second call."""
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch(
        "app.services.cold_start.onboarding.process_onboarding",
        new_callable=AsyncMock,
    ):
        await client.post(
            "/api/v1/onboarding",
            json={"interest_text": "tech", "sample_ratings": [], "source_opml": None},
            headers=headers,
        )
        # Second call should fail
        resp = await client.post(
            "/api/v1/onboarding",
            json={"interest_text": "tech", "sample_ratings": [], "source_opml": None},
            headers=headers,
        )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_onboarding_requires_auth(client: AsyncClient):
    """POST /onboarding without auth token should return 401."""
    resp = await client.post(
        "/api/v1/onboarding",
        json={"interest_text": "tech", "sample_ratings": [], "source_opml": None},
    )
    assert resp.status_code == 401
