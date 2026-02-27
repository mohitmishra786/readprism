from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CreatorTopicTrust(Base):
    """Per-user, per-creator, per-topic trust weights learned from behavioral signals."""

    __tablename__ = "creator_topic_trust"
    __table_args__ = (
        UniqueConstraint("user_id", "creator_id", "topic_label", name="uq_creator_topic_trust"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creators.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic_label: Mapped[str] = mapped_column(String, nullable=False)
    trust_weight: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    interaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
