"""Hosted billing state on users + processed webhook events (#173)

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-18 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

_TS = ("trial_ends_at", "plan_expires_at", "billing_event_at")
_STR = ("billing_provider", "billing_status", "billing_portal_url")
_INDEXED = ("billing_customer_id", "billing_subscription_id")


def upgrade() -> None:
    for name in _TS:
        op.add_column("users", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    for name in (*_STR, *_INDEXED):
        op.add_column("users", sa.Column(name, sa.String(), nullable=True))
    for name in _INDEXED:
        op.create_index(f"ix_users_{name}", "users", [name])
    op.create_table(
        "billing_events",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("billing_events")
    for name in _INDEXED:
        op.drop_index(f"ix_users_{name}", table_name="users")
    for name in (*_TS, *_STR, *_INDEXED):
        op.drop_column("users", name)
