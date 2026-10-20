"""users.reengagement_stage and reengagement_sent_at (#238)

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("reengagement_stage", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users", sa.Column("reengagement_sent_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "reengagement_sent_at")
    op.drop_column("users", "reengagement_stage")
