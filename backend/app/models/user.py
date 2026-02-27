from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, Integer, String, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_text: Mapped[str | None] = mapped_column(String, nullable=True)
    digest_frequency: Mapped[str] = mapped_column(String, default="daily")
    digest_time_morning: Mapped[time] = mapped_column(Time, default=time(7, 0))
    digest_max_items: Mapped[int] = mapped_column(Integer, default=12)
    serendipity_percentage: Mapped[int] = mapped_column(Integer, default=15)
    tier: Mapped[str] = mapped_column(String, default="free")
    timezone: Mapped[str] = mapped_column(String, default="UTC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
