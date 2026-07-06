from __future__ import annotations

import uuid
from datetime import UTC
from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_record_interaction_enqueues_graph_update(
    client: AsyncClient, test_user_data: dict, db_session
):
    from datetime import datetime, timezone

    from app.models.content import ContentItem

    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create a content item in DB and commit it so the endpoint's own session
    # (separate from db_session) can see it.
    content = ContentItem(
        url="https://test.com/article",
        title="Test Article",
        fetched_at=datetime.now(UTC),
    )
    db_session.add(content)
    await db_session.commit()

    with patch(
        "app.workers.tasks.update_interest_graph.update_interest_graph_for_interaction.delay"
    ) as mock_delay:
        resp = await client.post(
            "/api/v1/feedback/interaction",
            json={
                "content_item_id": str(content.id),
                "read_completion_pct": 0.95,
                "time_on_page_seconds": 480,
            },
            headers=headers,
        )

    assert resp.status_code == 200
    mock_delay.assert_called_once()
