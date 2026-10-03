"""Source suggestions (EC-06).

Candidates come from (a) sources of discovery items the user fully read and
(b) starter-pack feeds matching top interest clusters — both population-free.
Dismissed URLs are never suggested again (unique per user+url, any status).
"""

from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SourceSuggestion(Base):
    __tablename__ = "source_suggestions"
    __table_args__ = (
        # A URL decided once (accepted OR dismissed) never re-enters the pool;
        # matches uq_source_suggestions_user_url in migration 0021.
        UniqueConstraint("user_id", "url", name="uq_source_suggestions_user_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
