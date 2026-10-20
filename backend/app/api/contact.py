"""Contact and grievance information (#183)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(prefix="/contact", tags=["contact"])


class ContactInfo(BaseModel):
    grievance_contact_email: str | None = None


@router.get("", response_model=ContactInfo)
async def get_contact_info() -> ContactInfo:
    """Return public contact/grievance info for the instance (#183)."""
    settings = get_settings()
    email = settings.grievance_contact_email.strip()
    return ContactInfo(grievance_contact_email=email if email else None)
