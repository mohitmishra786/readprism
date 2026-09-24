"""store podcast transcript URL

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-24 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_items", sa.Column("transcript_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("content_items", "transcript_url")
