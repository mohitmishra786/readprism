"""phase 2 impressions, embedding identity, ranker history

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-25 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_items", sa.Column("embedding_model", sa.String(), nullable=True))
    op.add_column("content_items", sa.Column("embedding_dim", sa.Integer(), nullable=True))
    op.add_column("content_items", sa.Column("embedding_version", sa.String(), nullable=True))
    op.create_table(
        "digest_impressions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("digest_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("digests.id", ondelete="CASCADE"), nullable=True),
        sa.Column("section", sa.String(), nullable=False, server_default="feed"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("features_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("weights_version", sa.String(), nullable=False, server_default="2"),
        sa.Column("exploration", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("propensity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("viewed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("shown_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_digest_impressions_user_id", "digest_impressions", ["user_id"])
    op.create_table(
        "ranker_weight_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("weights", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ranker_weight_revisions_user_id", "ranker_weight_revisions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_ranker_weight_revisions_user_id", table_name="ranker_weight_revisions")
    op.drop_table("ranker_weight_revisions")
    op.drop_index("ix_digest_impressions_user_id", table_name="digest_impressions")
    op.drop_table("digest_impressions")
    op.drop_column("content_items", "embedding_version")
    op.drop_column("content_items", "embedding_dim")
    op.drop_column("content_items", "embedding_model")
