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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

try:
    from pgvector.sqlalchemy import Vector
    VECTOR_AVAILABLE = True
except ImportError:
    VECTOR_AVAILABLE = False


class InterestNode(Base):
    __tablename__ = "interest_nodes"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_label", name="uq_user_topic"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic_label: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=0.5)
    half_life_days: Mapped[int] = mapped_column(Integer, default=60)
    last_reinforced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_core: Mapped[bool] = mapped_column(Boolean, default=False)
    reinforcement_count: Mapped[int] = mapped_column(Integer, default=0)
    suppressed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
        topic_embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)


class InterestEdge(Base):
    __tablename__ = "interest_edges"
    __table_args__ = (
        UniqueConstraint("user_id", "from_node_id", "to_node_id", name="uq_user_edge"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interest_nodes.id", ondelete="CASCADE"), nullable=False
    )
    to_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interest_nodes.id", ondelete="CASCADE"), nullable=False
    )
    co_occurrence_count: Mapped[int] = mapped_column(Integer, default=0)
    edge_weight: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
