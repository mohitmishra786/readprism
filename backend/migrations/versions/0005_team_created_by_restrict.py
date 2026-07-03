"""change teams.created_by ondelete from CASCADE to RESTRICT

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-04 00:00:00.000000

CodeRabbit review: deleting a user shouldn't cascade-delete a team that other
members still actively use. RESTRICT forces an ownership transfer first.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop and recreate the FK with ondelete=RESTRICT. PostgreSQL doesn't support
    # altering FK behavior in place, so we drop and re-add.
    op.drop_constraint("teams_created_by_fkey", "teams", type_="foreignkey")
    op.create_foreign_key(
        "teams_created_by_fkey",
        "teams",
        "users",
        ["created_by"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("teams_created_by_fkey", "teams", type_="foreignkey")
    op.create_foreign_key(
        "teams_created_by_fkey",
        "teams",
        "users",
        ["created_by"],
        ["id"],
        ondelete="CASCADE",
    )
