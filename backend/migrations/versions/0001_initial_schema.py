"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-02-25 00:00:00.000000
"""
from __future__ import annotations

import uuid
from datetime import time

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

try:
    from pgvector.sqlalchemy import Vector
    VECTOR_AVAILABLE = True
except ImportError:
    VECTOR_AVAILABLE = False

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("onboarding_complete", sa.Boolean(), default=False),
        sa.Column("interest_text", sa.String(), nullable=True),
        sa.Column("digest_frequency", sa.String(), default="daily"),
        sa.Column("digest_time_morning", sa.Time(), default=time(7, 0)),
        sa.Column("digest_max_items", sa.Integer(), default=12),
        sa.Column("serendipity_percentage", sa.Integer(), default=15),
        sa.Column("tier", sa.String(), default="free"),
        sa.Column("timezone", sa.String(), default="UTC"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # sources
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("feed_url", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(), default="rss"),
        sa.Column("trust_weight", sa.Float(), default=0.5),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetch_error_count", sa.Integer(), default=0),
        sa.Column("topics", postgresql.JSONB(), default=list),
        sa.Column("priority", sa.String(), default="normal"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # creators
    op.create_table(
        "creators",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("resolved", sa.Boolean(), default=False),
        sa.Column("priority", sa.String(), default="normal"),
        sa.Column("trust_weight", sa.Float(), default=0.5),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # creator_platforms
    op.create_table(
        "creator_platforms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("creator_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("creators.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("platform_url", sa.String(), nullable=False),
        sa.Column("feed_url", sa.String(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), default=False),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # content_items
    content_columns = [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("creator_platform_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("creator_platforms.id", ondelete="SET NULL"), nullable=True),
        sa.Column("url", sa.String(), nullable=False, unique=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column("summary_headline", sa.String(), nullable=True),
        sa.Column("summary_brief", sa.Text(), nullable=True),
        sa.Column("summary_detailed", sa.Text(), nullable=True),
        sa.Column("reading_time_minutes", sa.Integer(), nullable=True),
        sa.Column("content_depth_score", sa.Float(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("has_citations", sa.Boolean(), default=False),
        sa.Column("is_original_reporting", sa.Boolean(), nullable=True),
        sa.Column("topic_clusters", postgresql.JSONB(), default=list),
        sa.Column("summarization_cached", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    ]
    if VECTOR_AVAILABLE:
        content_columns.append(sa.Column("embedding", Vector(384), nullable=True))
    else:
        content_columns.append(sa.Column("embedding", sa.Text(), nullable=True))

    op.create_table("content_items", *content_columns)
    op.create_index("ix_content_items_url", "content_items", ["url"])

    # user_content_interactions
    op.create_table(
        "user_content_interactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prs_score", sa.Float(), nullable=True),
        sa.Column("was_suggested", sa.Boolean(), default=False),
        sa.Column("surfaced_in_digest", sa.Boolean(), default=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_completion_pct", sa.Float(), nullable=True),
        sa.Column("time_on_page_seconds", sa.Integer(), nullable=True),
        sa.Column("re_read_count", sa.Integer(), default=0),
        sa.Column("explicit_rating", sa.Integer(), nullable=True),
        sa.Column("explicit_rating_reason", sa.String(), nullable=True),
        sa.Column("saved", sa.Boolean(), default=False),
        sa.Column("saved_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shared", sa.Boolean(), default=False),
        sa.Column("skipped", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "content_item_id", name="uq_user_content"),
    )

    # interest_nodes
    interest_node_columns = [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_label", sa.String(), nullable=False),
        sa.Column("weight", sa.Float(), default=0.5),
        sa.Column("half_life_days", sa.Integer(), default=60),
        sa.Column("last_reinforced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_core", sa.Boolean(), default=False),
        sa.Column("reinforcement_count", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "topic_label", name="uq_user_topic"),
    ]
    if VECTOR_AVAILABLE:
        interest_node_columns.append(sa.Column("topic_embedding", Vector(384), nullable=True))
    else:
        interest_node_columns.append(sa.Column("topic_embedding", sa.Text(), nullable=True))

    op.create_table("interest_nodes", *interest_node_columns)

    # interest_edges
    op.create_table(
        "interest_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("interest_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("interest_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("co_occurrence_count", sa.Integer(), default=0),
        sa.Column("edge_weight", sa.Float(), default=0.0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "from_node_id", "to_node_id", name="uq_user_edge"),
    )

    # digests
    op.create_table(
        "digests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_method", sa.String(), default="in_app"),
        sa.Column("section_counts", postgresql.JSONB(), default=dict),
        sa.Column("opened", sa.Boolean(), default=False),
        sa.Column("total_items", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # digest_items
    op.create_table(
        "digest_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("digest_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("digests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("prs_score", sa.Float(), nullable=False),
        sa.Column("signal_breakdown", postgresql.JSONB(), default=dict),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # HNSW indexes for vector similarity (pgvector)
    if VECTOR_AVAILABLE:
        op.execute("CREATE INDEX ON content_items USING hnsw (embedding vector_cosine_ops)")
        op.execute("CREATE INDEX ON interest_nodes USING hnsw (topic_embedding vector_cosine_ops)")


def downgrade() -> None:
    op.drop_table("digest_items")
    op.drop_table("digests")
    op.drop_table("interest_edges")
    op.drop_table("interest_nodes")
    op.drop_table("user_content_interactions")
    op.drop_table("content_items")
    op.drop_table("creator_platforms")
    op.drop_table("creators")
    op.drop_table("sources")
    op.drop_table("users")
