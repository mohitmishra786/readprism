"""interaction graph_signal_applied (#105)

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-18 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_content_interactions",
        sa.Column("graph_signal_applied", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_content_interactions", "graph_signal_applied")
