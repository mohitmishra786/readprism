"""source suggestions (EC-06)

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_source_suggestions_user_id", "source_suggestions", ["user_id"])
    op.create_index(
        "uq_source_suggestions_user_url",
        "source_suggestions",
        ["user_id", "url"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_source_suggestions_user_url", table_name="source_suggestions")
    op.drop_index("ix_source_suggestions_user_id", table_name="source_suggestions")
    op.drop_table("source_suggestions")
