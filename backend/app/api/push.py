"""Web Push digest alerts (#266): opt-in per device."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.push import PushSubscription
from app.models.user import User
from app.services import push

router = APIRouter(prefix="/push", tags=["push"])


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(..., min_length=40, max_length=200)
    auth: str = Field(..., min_length=16, max_length=64)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(..., max_length=2000)
    keys: SubscriptionKeys


class EndpointIn(BaseModel):
    endpoint: str = Field(..., max_length=2000)


def _require_enabled() -> None:
    if not push.push_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Push alerts are not set up here"
        )


@router.get("/public-key")
async def public_key(current_user: User = Depends(get_current_user)) -> dict:
    """The VAPID key the browser subscribes with; 404 when push is off."""
    from app.config import get_settings

    _require_enabled()
    return {"public_key": get_settings().vapid_public_key.strip()}


@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe(
    body: SubscriptionIn,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Opt this device in. Re-subscribing the same endpoint moves it to you."""
    _require_enabled()
    if not push.endpoint_allowed(body.endpoint):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Not a public https push endpoint"
        )
    try:
        push.b64url_decode(body.keys.p256dh)
        push.b64url_decode(body.keys.auth)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid keys")
    existing = (
        await session.execute(
            select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = PushSubscription(
            endpoint=body.endpoint, user_id=current_user.id, p256dh="", auth=""
        )
        session.add(existing)
    existing.user_id = current_user.id
    existing.p256dh = body.keys.p256dh
    existing.auth = body.keys.auth
    existing.failure_count = 0
    await session.flush()
    return {"status": "subscribed"}


@router.post("/unsubscribe")
async def unsubscribe(
    body: EndpointIn,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Opt this device out (only your own subscription)."""
    await session.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint,
            PushSubscription.user_id == current_user.id,
        )
    )
    return {"status": "unsubscribed"}


@router.post("/test")
async def send_test(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Send a test alert to all of your opted-in devices."""
    _require_enabled()
    counts = await push.notify_user(
        session,
        current_user.id,
        {"title": "Weirling", "body": "Digest alerts are on for this device.", "url": "/digest"},
    )
    return counts
