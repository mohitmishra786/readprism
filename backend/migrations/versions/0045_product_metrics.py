"""product_events, product_metrics_daily (#131)

Revision ID: 0045
Revises: 0044
Create Date: 2026-10-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("props", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_product_events_user_id", "product_events", ["user_id"])
    op.create_index("ix_product_events_event", "product_events", ["event"])
    op.create_index("ix_product_events_created_at", "product_events", ["created_at"])
    op.create_table(
        "product_metrics_daily",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("metric", sa.String(), primary_key=True),
        sa.Column("value", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("product_metrics_daily")
    op.drop_table("product_events")
