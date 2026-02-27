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
    digest_max_items: int
    serendipity_percentage: int
    tier: str
    timezone: str
    created_at: datetime


class UserUpdate(BaseModel):
    display_name: str | None = None
    digest_frequency: str | None = None
    digest_time_morning: time | None = None
    digest_max_items: int | None = None
    serendipity_percentage: int | None = None
    timezone: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400


class TokenRefresh(BaseModel):
    refresh_token: str
