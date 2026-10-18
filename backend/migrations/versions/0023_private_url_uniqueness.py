"""URL unique per public row and per owner for private rows (#101)

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-18 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows are globally unique by URL, so both partial indexes build
    # without conflicts. Create them before dropping the old constraint so the
    # table is never unprotected.
    op.create_index(
        "uq_content_items_public_url",
        "content_items",
        ["url"],
        unique=True,
        postgresql_where=sa.text("owner_user_id IS NULL"),
    )
    op.create_index(
        "uq_content_items_private_url",
        "content_items",
        ["owner_user_id", "url"],
        unique=True,
        postgresql_where=sa.text("owner_user_id IS NOT NULL"),
    )
    op.drop_constraint("content_items_url_key", "content_items", type_="unique")


def downgrade() -> None:
    # Fails if several users now hold private rows for the same URL (or a
    # private and a public row share one); resolve those duplicates first.
    op.create_unique_constraint("content_items_url_key", "content_items", ["url"])
    op.drop_index("uq_content_items_private_url", table_name="content_items")
    op.drop_index("uq_content_items_public_url", table_name="content_items")
