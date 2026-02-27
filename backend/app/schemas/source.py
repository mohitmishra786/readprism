from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, HttpUrl


class SourceCreate(BaseModel):
    url: str
    priority: str = "normal"
    topics: list[str] = []


class SourceUpdate(BaseModel):
    priority: str | None = None
    trust_weight: float | None = None
    is_active: bool | None = None
    topics: list[str] | None = None


class SourceRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    url: str
    name: str | None
    feed_url: str | None
    source_type: str
    trust_weight: float
    is_active: bool
    last_fetched_at: datetime | None
    fetch_error_count: int
    topics: list
    priority: str
    created_at: datetime
