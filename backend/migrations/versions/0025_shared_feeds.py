"""shared feeds: one row per feed, subscriptions point at it (#161, #163)

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-18 00:00:00.000000

Data migration (#163): every non-newsletter source becomes a subscription of
the feed with its coalesce(feed_url, url) key. The feed's poll state comes
from the subscriber that fetched most recently. Content items get the feed id
of the source that stored them. Interactions, digests and trust are not
touched. Downgrade drops the new table and columns; no per-user data lives
only in them (poll state stays mirrored on sources).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feeds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("feed_url", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("http_etag", sa.String(), nullable=True),
        sa.Column("http_last_modified", sa.String(), nullable=True),
        sa.Column("poll_interval_seconds", sa.Integer(), server_default="3600", nullable=False),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recent_gap_seconds", postgresql.JSONB(), nullable=True),
        sa.Column("feed_status", sa.String(), server_default="healthy", nullable=False),
        sa.Column("failure_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("dead_notice_pending", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("fetch_error_count", sa.Integer(), nullable=True),
        sa.Column("initial_backfill_done", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_feeds_key", "feeds", ["key"], unique=True)
    op.add_column(
        "sources",
        sa.Column("feed_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("feeds.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_sources_feed_id", "sources", ["feed_id"])
    op.add_column(
        "content_items",
        sa.Column("feed_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("feeds.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_content_items_feed_id", "content_items", ["feed_id"])

    # One feed per distinct key; poll state from the most recently fetched subscriber.
    op.execute(
        """
        INSERT INTO feeds (id, key, url, feed_url, source_type, is_active, last_fetched_at,
                           http_etag, http_last_modified, poll_interval_seconds, next_poll_at,
                           recent_gap_seconds, feed_status, failure_since, last_error_at,
                           last_error, dead_notice_pending, fetch_error_count,
                           initial_backfill_done)
        SELECT DISTINCT ON (coalesce(s.feed_url, s.url))
               gen_random_uuid(), coalesce(s.feed_url, s.url), s.url, s.feed_url, s.source_type,
               true, s.last_fetched_at, s.http_etag, s.http_last_modified,
               coalesce(s.poll_interval_seconds, 3600), s.next_poll_at, s.recent_gap_seconds,
               coalesce(s.feed_status, 'healthy'), s.failure_since, s.last_error_at, s.last_error,
               false, coalesce(s.fetch_error_count, 0), coalesce(s.initial_backfill_done, true)
        FROM sources s
        WHERE s.source_type IS DISTINCT FROM 'newsletter'
        ORDER BY coalesce(s.feed_url, s.url), s.last_fetched_at DESC NULLS LAST
        """
    )
    op.execute(
        """
        UPDATE sources s SET feed_id = f.id
        FROM feeds f
        WHERE f.key = coalesce(s.feed_url, s.url)
          AND s.source_type IS DISTINCT FROM 'newsletter'
        """
    )
    op.execute(
        """
        UPDATE content_items c SET feed_id = s.feed_id
        FROM sources s
        WHERE c.source_id = s.id AND s.feed_id IS NOT NULL AND c.owner_user_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_content_items_feed_id", table_name="content_items")
    op.drop_column("content_items", "feed_id")
    op.drop_index("ix_sources_feed_id", table_name="sources")
    op.drop_column("sources", "feed_id")
    op.drop_index("ix_feeds_key", table_name="feeds")
    op.drop_table("feeds")
