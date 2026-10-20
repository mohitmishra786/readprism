"""users.quota_overrides (#172)

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("quota_overrides", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "quota_overrides")
