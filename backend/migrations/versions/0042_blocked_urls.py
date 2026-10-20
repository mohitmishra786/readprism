"""blocked_urls (#183)

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blocked_urls",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("url_key", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_blocked_urls_url_key", "blocked_urls", ["url_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_blocked_urls_url_key", table_name="blocked_urls")
    op.drop_table("blocked_urls")
