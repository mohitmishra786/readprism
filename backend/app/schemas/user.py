from __future__ import annotations

import uuid
from datetime import datetime, time

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    display_name: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: str
    display_name: str | None
    onboarding_complete: bool
    digest_frequency: str
    digest_time_morning: time
    send_time_locked: bool
    digest_max_items: int
    digest_length_locked: bool
    serendipity_percentage: int
    preferred_languages: list[str]
    tier: str
    timezone: str
    created_at: datetime


class UserUpdate(BaseModel):
    display_name: str | None = None
    digest_frequency: str | None = None
    digest_time_morning: time | None = None
    # False locks digest_time_morning to the explicit value above; True hands
    # the send time back to the learned-histogram job (UX-03).
    send_time_auto: bool | None = None
    digest_max_items: int | None = None
    # False locks digest_max_items to the explicit value above; True hands the
    # length back to the learner (UX-02).
    digest_length_auto: bool | None = None
    serendipity_percentage: int | None = None
    preferred_languages: list[str] | None = None
    timezone: str | None = None


class Token(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int = 1800


class TokenRefresh(BaseModel):
    refresh_token: str


class MagicLinkRequest(BaseModel):
    email: EmailStr
    display_name: str | None = None


class MagicLinkVerify(BaseModel):
    token: str
