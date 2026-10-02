"""FTS column for hybrid search (UX-11)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Weighted tsvector generated on write: title (A) dominates, summaries (B)
    # follow. full_text is deliberately excluded — it is large and pruned by
    # retention, which would silently churn the index.
    op.add_column(
        "content_items",
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR,
            sa.Computed(
                "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('english', coalesce(summary_headline, '') || ' ' || coalesce(summary_brief, '')), 'B')",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.execute("CREATE INDEX ix_content_items_search_tsv ON content_items USING GIN (search_tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_content_items_search_tsv")
    op.drop_column("content_items", "search_tsv")
