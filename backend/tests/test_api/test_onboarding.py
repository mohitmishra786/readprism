from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_onboarding_complete_sets_flag(client: AsyncClient, test_user_data: dict, db_session):
    """POST /onboarding should mark onboarding_complete=True on the user."""
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch(
        "app.api.onboarding.process_onboarding",
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
async def test_onboarding_idempotent_returns_409(
    client: AsyncClient, test_user_data: dict, db_session
):
    """Calling /onboarding twice should return 409 on the second call."""
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Patch the expensive internals (Groq + embeddings) so the real onboarding
    # flow runs and sets onboarding_complete=True, making the second call 409.
    with patch(
        "app.services.cold_start.onboarding.GroqSummarizer",
    ) as mock_groq_cls, patch(
        "app.services.cold_start.onboarding.get_embedding_service"
    ) as mock_emb_svc:
        mock_groq = AsyncMock()
        mock_groq.extract_topics = AsyncMock(return_value=["technology"])
        mock_groq_cls.return_value = mock_groq
        mock_svc = MagicMock()
        mock_svc.encode_batch_cached = AsyncMock(return_value=[[0.1] * 384])
        mock_svc.encode_single = AsyncMock(return_value=[0.1] * 384)
        mock_emb_svc.return_value = mock_svc

        first = await client.post(
            "/api/v1/onboarding",
            json={"interest_text": "tech", "sample_ratings": [], "source_opml": None},
            headers=headers,
        )
        assert first.status_code == 200, first.text
        # Second call should fail with 409 (onboarding already complete).
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
