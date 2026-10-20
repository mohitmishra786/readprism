from __future__ import annotations

import uuid
from datetime import datetime, time

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    display_name: str | None = None
    # Required when REGISTRATION_MODE=invite (#153).
    invite_code: str | None = None
    # Consent to Terms of Service and Privacy Policy (#181). Required on hosted.
    accept_terms: bool = False


class UserLogin(BaseModel):
    # Plain str, not EmailStr: the seeded demo persona uses a .local address,
    # which EmailStr rejects with 422 (#159). Login is an exact lookup, so any
    # string is safe; the cap just bounds the payload.
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(max_length=1024)


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
    # False only while this instance requires verification and it is pending (#175).
    email_verified: bool = True
    fetch_paused_until: datetime | None = None
    collaborative_opt_out: bool = False
    weekly_email: bool = False
    is_demo: bool = False


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
    collaborative_opt_out: bool | None = None
    weekly_email: bool | None = None


class Token(BaseModel):
    # Empty in cookie mode (#103): the browser holds the credentials in
    # httpOnly cookies and only receives the CSRF token.
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int = 1800
    csrf_token: str | None = None


class TokenRefresh(BaseModel):
    # Optional: cookie-mode clients send the refresh token as a cookie instead.
    refresh_token: str | None = None


class MagicLinkRequest(BaseModel):
    email: EmailStr
    display_name: str | None = None
    # A magic link can also create an account; on hosted that needs consent
    # to the Terms and Privacy policy, like /register (#181).
    accept_terms: bool = False


class MagicLinkVerify(BaseModel):
    token: str


class EmailVerify(BaseModel):
    token: str
