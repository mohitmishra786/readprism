from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

try:
    from pgvector.sqlalchemy import Vector
    VECTOR_AVAILABLE = True
except ImportError:
    VECTOR_AVAILABLE = False


class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    creator_platform_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creator_platforms.id", ondelete="SET NULL"), nullable=True, index=True
    )
    url: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_headline: Mapped[str | None] = mapped_column(String, nullable=True)
    summary_brief: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_detailed: Mapped[str | None] = mapped_column(Text, nullable=True)
    reading_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_depth_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_citations: Mapped[bool] = mapped_column(Boolean, default=False)
    is_original_reporting: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    topic_clusters: Mapped[list] = mapped_column(JSONB, default=list)
    summarization_cached: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    if VECTOR_AVAILABLE:
        embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)


class UserContentInteraction(Base):
    __tablename__ = "user_content_interactions"
    __table_args__ = (
        UniqueConstraint("user_id", "content_item_id", name="uq_user_content"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prs_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    was_suggested: Mapped[bool] = mapped_column(Boolean, default=False)
    surfaced_in_digest: Mapped[bool] = mapped_column(Boolean, default=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_completion_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_on_page_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    re_read_count: Mapped[int] = mapped_column(Integer, default=0)
    explicit_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    explicit_rating_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    saved_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
