"""Reading on the original site (#157): record the open, learn only from the answer."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction


@pytest.mark.asyncio
async def test_outbound_click_records_the_open_but_teaches_nothing(client, db_session):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": f"ob{uuid.uuid4().hex[:6]}@example.com", "password": "TestPass123!"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    item = ContentItem(url=f"https://pay.example/{uuid.uuid4().hex}", title="T", paywalled=True)
    db_session.add(item)
    await db_session.commit()

    target = "app.workers.tasks.update_interest_graph.update_interest_graph_for_interaction.delay"
    with patch(target) as learn:
        out = await client.post(
            "/api/v1/feedback/interaction",
            json={"content_item_id": str(item.id), "opened_externally": True},
            headers=headers,
        )
        assert out.status_code == 200
        learn.assert_not_called()  # a bare click is not a bounce

        back = await client.post(
            "/api/v1/feedback/interaction",
            json={"content_item_id": str(item.id), "read_completion_pct": 1.0, "reached_end": True},
            headers=headers,
        )
        assert back.status_code == 200
        learn.assert_called_once()

    ix = (
        await db_session.execute(
            select(UserContentInteraction).where(UserContentInteraction.content_item_id == item.id)
        )
    ).scalar_one()
    assert ix.opened_at is not None and ix.read_completion_pct == 1.0 and ix.reached_end
