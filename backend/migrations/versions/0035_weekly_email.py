"""users.weekly_email and weekly_email_sent_at (#184)

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("weekly_email", sa.Boolean(), nullable=False, server_default="false")
    )
    op.add_column(
        "users", sa.Column("weekly_email_sent_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "weekly_email_sent_at")
    op.drop_column("users", "weekly_email")
