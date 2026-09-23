"""per-source poll schedule

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-24 00:00:00.000000

Interval, next run, recent inter-item gaps, and the health label used by the
scheduler. Reversible.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="3600"),
    )
    op.add_column("sources", sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "sources",
        sa.Column("recent_gap_seconds", JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "sources",
        sa.Column("feed_status", sa.String(), nullable=False, server_default="healthy"),
    )
    op.add_column("sources", sa.Column("failure_since", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "failure_since")
    op.drop_column("sources", "feed_status")
    op.drop_column("sources", "recent_gap_seconds")
    op.drop_column("sources", "next_poll_at")
    op.drop_column("sources", "poll_interval_seconds")
