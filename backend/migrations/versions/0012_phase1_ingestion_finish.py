"""phase 1 ingestion columns: identity, extraction, newsletter token

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-25 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_items", sa.Column("guid", sa.String(), nullable=True))
    op.add_column("content_items", sa.Column("simhash", sa.String(length=16), nullable=True))
    op.add_column("content_items", sa.Column("extraction_method", sa.String(length=32), nullable=True))
    op.add_column("content_items", sa.Column("extraction_confidence", sa.Float(), nullable=True))
    op.add_column("content_items", sa.Column("page_type", sa.String(length=32), nullable=True))
    op.add_column("content_items", sa.Column("language", sa.String(length=16), nullable=True))
    op.add_column("content_items", sa.Column("lead_image_url", sa.String(), nullable=True))
    op.add_column(
        "content_items",
        sa.Column("paywalled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "content_items",
        sa.Column("rankable", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "content_items",
        sa.Column("origin", sa.String(length=32), nullable=False, server_default="followed"),
    )
    op.add_column("content_items", sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_content_source_guid", "content_items", ["source_id", "guid"])
    op.add_column(
        "sources",
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.add_column(
        "sources",
        sa.Column("initial_backfill_done", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("users", sa.Column("newsletter_token", sa.String(), nullable=True))
    op.create_unique_constraint("uq_users_newsletter_token", "users", ["newsletter_token"])


def downgrade() -> None:
    op.drop_constraint("uq_users_newsletter_token", "users", type_="unique")
    op.drop_column("users", "newsletter_token")
    op.drop_column("sources", "initial_backfill_done")
    op.drop_column("sources", "tags")
    op.drop_constraint("uq_content_source_guid", "content_items", type_="unique")
    for name in (
        "scored_at",
        "origin",
        "rankable",
        "paywalled",
        "lead_image_url",
        "language",
        "page_type",
        "extraction_confidence",
        "extraction_method",
        "simhash",
        "guid",
    ):
        op.drop_column("content_items", name)
