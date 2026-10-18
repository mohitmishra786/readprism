"""content_items.discovered_via (#141)

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-18 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_items", sa.Column("discovered_via", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("content_items", "discovered_via")
