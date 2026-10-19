"""user_content_interactions.tags (#150)

The user's own tags on a saved item (e.g. from a Pocket export). They live on
the user's interaction row because content rows can be shared public rows.

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_content_interactions", sa.Column("tags", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_content_interactions", "tags")
