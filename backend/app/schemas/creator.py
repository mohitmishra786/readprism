from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator


class CreatorPlatformRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    creator_id: uuid.UUID
    platform: str
    platform_url: str
    feed_url: str | None
    is_verified: bool
    last_fetched_at: datetime | None
    # Honesty layer: tells the UI how reliably this platform can be tracked.
    # fully_tracked / best_effort / unsupported. Derived from PLATFORM_CAPABILITIES.
    tracking_tier: str | None = None
    display_label: str | None = None

    @model_validator(mode="after")
    def _populate_platform_capabilities(self) -> "CreatorPlatformRead":
        # Late import avoids a circular dependency at module load time.
        from app.services.creator.resolver import PLATFORM_CAPABILITIES

        caps = PLATFORM_CAPABILITIES.get(self.platform)
        if caps:
            if self.tracking_tier is None:
                self.tracking_tier = caps["tracking_tier"]
            if self.display_label is None:
                self.display_label = caps["display_label"]
        else:
            if self.tracking_tier is None:
                self.tracking_tier = "best_effort"
            if self.display_label is None:
                self.display_label = self.platform.title()
        return self


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
