"""impression_rollups: de-identified daily impression counts (#224)

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-18 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "impression_rollups",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("section", sa.String(), primary_key=True),
        sa.Column("team", sa.String(16), primary_key=True, server_default=""),
        sa.Column("exploration", sa.Boolean(), primary_key=True, server_default=sa.false()),
        sa.Column("shown", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("viewed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_digest_impressions_shown_at", "digest_impressions", ["shown_at"])


def downgrade() -> None:
    op.drop_index("ix_digest_impressions_shown_at", table_name="digest_impressions")
    op.drop_table("impression_rollups")
