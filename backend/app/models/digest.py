from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DigestFeedbackPrompt(Base):
    """Conversational feedback prompts shown in early-user digests (first 14 days)."""

    __tablename__ = "digest_feedback_prompts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    digest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("digests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="CASCADE"), nullable=True
    )
    prompt_text: Mapped[str] = mapped_column(String, nullable=False)
    prompt_type: Mapped[str] = mapped_column(String, nullable=False)  # depth_level, source_quality, topic_accuracy
    answered: Mapped[bool] = mapped_column(Boolean, default=False)
    answer: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_method: Mapped[str] = mapped_column(String, default="in_app")
    section_counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    opened: Mapped[bool] = mapped_column(Boolean, default=False)
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DigestItem(Base):
    __tablename__ = "digest_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    digest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("digests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(String, nullable=False)
    prs_score: Mapped[float] = mapped_column(Float, nullable=False)
    signal_breakdown: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
