"""pairwise learner state (#154) and interleaving team (#130)

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-18 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_meta_weights",
        sa.Column("pairs_seen", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "user_meta_weights",
        sa.Column("trained_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("digest_impressions", sa.Column("team", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("digest_impressions", "team")
    op.drop_column("user_meta_weights", "trained_until")
    op.drop_column("user_meta_weights", "pairs_seen")
