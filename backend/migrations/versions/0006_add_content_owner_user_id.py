"""add owner_user_id to content_items for per-user private content

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-21 00:00:00.000000

Newsletter-sourced content is personalized (recipient name, unsubscribe tokens)
and must not be deduped into shared rows or surfaced to other users. owner_user_id
tags such private content with its owner; NULL means public/shared content
(RSS/scraped). Enforced in the discovery pool, content-detail access, and
semantic dedup (audit 06-6).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_items",
        sa.Column("owner_user_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_content_items_owner_user_id", "content_items", ["owner_user_id"]
    )
    op.create_foreign_key(
        "fk_content_items_owner_user_id_users",
        "content_items",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_content_items_owner_user_id_users", "content_items", type_="foreignkey"
    )
    op.drop_index("ix_content_items_owner_user_id", table_name="content_items")
    op.drop_column("content_items", "owner_user_id")
