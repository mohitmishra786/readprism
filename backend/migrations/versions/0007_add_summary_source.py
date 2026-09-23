"""add summary_source to content_items

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-24 00:00:00.000000

Records whether a stored summary came from the LLM or the extractive fallback.
Nullable so existing rows stay valid; new writes set llm or extractive.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_items",
        sa.Column("summary_source", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("content_items", "summary_source")
