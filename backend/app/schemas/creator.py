from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class CreatorPlatformRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    creator_id: uuid.UUID
    platform: str
    platform_url: str
    feed_url: str | None
    is_verified: bool
    last_fetched_at: datetime | None


class CreatorCreate(BaseModel):
    name_or_url: str
    priority: str = "normal"


class CreatorUpdate(BaseModel):
    priority: str | None = None
    display_name: str | None = None


class CreatorRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    resolved: bool
    priority: str
    trust_weight: float
    platforms: list[CreatorPlatformRead] = []
    created_at: datetime


class CreatorResolutionResult(BaseModel):
    creator: CreatorRead
    platforms_discovered: int
    warning: str | None = None
