"""store ETag and Last-Modified per source

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-24 00:00:00.000000

Conditional GET. Both columns are nullable and reversible.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("http_etag", sa.String(), nullable=True))
    op.add_column("sources", sa.Column("http_last_modified", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "http_last_modified")
    op.drop_column("sources", "http_etag")
