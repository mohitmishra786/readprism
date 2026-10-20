"""sources.list_unsubscribe and newsletter_delivery (#249)

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("list_unsubscribe", sa.String(), nullable=True))
    op.add_column("sources", sa.Column("newsletter_delivery", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "newsletter_delivery")
    op.drop_column("sources", "list_unsubscribe")
