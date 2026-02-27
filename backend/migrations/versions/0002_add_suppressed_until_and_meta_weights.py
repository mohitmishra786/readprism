"""add suppressed_until to interest_nodes and user_meta_weights table

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-28 00:00:00.000000
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add suppressed_until column to interest_nodes
    op.add_column(
        "interest_nodes",
        sa.Column("suppressed_until", sa.DateTime(timezone=True), nullable=True),
    )

    # Create user_meta_weights table for persistent storage of learned weights
    op.create_table(
        "user_meta_weights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("weights", postgresql.JSONB(), nullable=False),
        sa.Column("update_count", sa.Integer(), default=0, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_user_meta_weights_user_id", "user_meta_weights", ["user_id"])

    # Add creator_topic_trust table for per-creator-per-topic trust weights
    op.create_table(
        "creator_topic_trust",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "creator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("creators.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("topic_label", sa.String(), nullable=False),
        sa.Column("trust_weight", sa.Float(), default=0.5, nullable=False),
        sa.Column("interaction_count", sa.Integer(), default=0, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "creator_id", "topic_label", name="uq_creator_topic_trust"),
    )

    # Add digest_feedback_prompts table for early-user prompts
    op.create_table(
        "digest_feedback_prompts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "digest_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("digests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "content_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_items.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("prompt_text", sa.String(), nullable=False),
        sa.Column("prompt_type", sa.String(), nullable=False),  # depth_level, source_quality, topic_accuracy
        sa.Column("answered", sa.Boolean(), default=False),
        sa.Column("answer", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_digest_feedback_prompts_digest_id", "digest_feedback_prompts", ["digest_id"])


def downgrade() -> None:
    op.drop_table("digest_feedback_prompts")
    op.drop_table("creator_topic_trust")
    op.drop_index("ix_user_meta_weights_user_id", table_name="user_meta_weights")
    op.drop_table("user_meta_weights")
    op.drop_column("interest_nodes", "suppressed_until")
