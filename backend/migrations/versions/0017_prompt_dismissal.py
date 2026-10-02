"""prompt dismissal (UX-07)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "digest_feedback_prompts",
        sa.Column("dismissed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("digest_feedback_prompts", "dismissed")
