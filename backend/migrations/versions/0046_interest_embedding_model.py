"""interest_nodes.embedding_model (#244)

Revision ID: 0046
Revises: 0045
Create Date: 2026-10-21 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL means a legacy MiniLM vector, so existing rows need no backfill.
    op.add_column("interest_nodes", sa.Column("embedding_model", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("interest_nodes", "embedding_model")
