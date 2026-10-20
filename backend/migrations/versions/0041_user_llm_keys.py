"""user_llm_keys (#255)

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_llm_keys",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column("key_encrypted", sa.Text(), nullable=False),
        sa.Column("key_last4", sa.String(), nullable=False, server_default=""),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("user_llm_keys")
