"""add reading telemetry columns to user_content_interactions

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-03 00:00:00.000000

Adds scroll_depth_pct, active_time_seconds, reached_end to
user_content_interactions. These are populated by the new in-app reading
telemetry (useReadingTelemetry) and take precedence over the legacy
time-on-page heuristic in the reading_depth signal.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_content_interactions",
        sa.Column("scroll_depth_pct", sa.Float(), nullable=True),
    )
    op.add_column(
        "user_content_interactions",
        sa.Column("active_time_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "user_content_interactions",
        sa.Column(
            "reached_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("user_content_interactions", "reached_end")
    op.drop_column("user_content_interactions", "active_time_seconds")
    op.drop_column("user_content_interactions", "scroll_depth_pct")
