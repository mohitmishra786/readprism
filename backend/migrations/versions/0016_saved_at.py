"""saved_at timestamp for saved-queue semantics (UX-12)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_content_interactions",
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill: rows already saved get their creation time as best-known save time.
    op.execute("UPDATE user_content_interactions SET saved_at = created_at WHERE saved = true")


def downgrade() -> None:
    op.drop_column("user_content_interactions", "saved_at")
