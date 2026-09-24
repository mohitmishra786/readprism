"""last error and one-time dead-source notice

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-24 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("last_error", sa.String(), nullable=True))
    op.add_column(
        "sources",
        sa.Column("dead_notice_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("sources", "dead_notice_pending")
    op.drop_column("sources", "last_error")
    op.drop_column("sources", "last_error_at")
