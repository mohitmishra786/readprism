from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    feed_url: Mapped[str | None] = mapped_column(String, nullable=True)
    source_type: Mapped[str] = mapped_column(String, default="rss")
    trust_weight: Mapped[float] = mapped_column(Float, default=0.5)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Conditional GET validators. Sent back as If-None-Match / If-Modified-Since.
    http_etag: Mapped[str | None] = mapped_column(String, nullable=True)
    http_last_modified: Mapped[str | None] = mapped_column(String, nullable=True)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=3600, server_default="3600")
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recent_gap_seconds: Mapped[list] = mapped_column(JSONB, default=list)
    feed_status: Mapped[str] = mapped_column(String, default="healthy", server_default="healthy")
    failure_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    # Set when the feed first becomes dead. Cleared after the digest footer mentions it.
    dead_notice_pending: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    fetch_error_count: Mapped[int] = mapped_column(Integer, default=0)
    topics: Mapped[list] = mapped_column(JSONB, default=list)
    priority: Mapped[str] = mapped_column(String, default="normal")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def health(self) -> str:
        """Scheduler label: healthy, degraded, failing, or dead."""
        return self.feed_status or "healthy"
