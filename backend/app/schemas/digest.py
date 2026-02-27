from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.content import ContentItemRead


class DigestItemRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    digest_id: uuid.UUID
    content_item_id: uuid.UUID
    position: int
    section: str
    prs_score: float
    signal_breakdown: dict
    content: ContentItemRead | None = None


class DigestRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    generated_at: datetime
    delivered_at: datetime | None
    delivery_method: str
    section_counts: dict
    opened: bool
    total_items: int
    items: list[DigestItemRead] = []
    created_at: datetime
