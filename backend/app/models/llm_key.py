"""A reader's own LLM key on hosted (#255), encrypted at rest."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserLLMKey(Base):
    __tablename__ = "user_llm_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # One of BYOK_ALLOWED_BASE_URLS.
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    # Fernet token (app.utils.secretbox, purpose "user-llm-key").
    key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    key_last4: Mapped[str] = mapped_column(String, nullable=False, default="")
    # Model for this reader's summaries; empty = the instance's summary model.
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
