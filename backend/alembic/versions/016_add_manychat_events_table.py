"""Add manychat_events table for webhook event tracking.

Revision ID: 016_manychat_events
Revises: 015_widen_metric_nums
Create Date: 2026-04-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "016_manychat_events"
down_revision: Union[str, None] = "015_widen_metric_nums"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "manychat_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manychat_subscriber_id", sa.String(length=255), nullable=False),
        sa.Column("flow_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_manychat_events_org_id", "manychat_events", ["org_id"], unique=False)
    op.create_index("ix_manychat_events_manychat_subscriber_id", "manychat_events", ["manychat_subscriber_id"], unique=False)
    op.create_index("ix_manychat_events_flow_id", "manychat_events", ["flow_id"], unique=False)
    op.create_index("ix_manychat_events_event_type", "manychat_events", ["event_type"], unique=False)
    op.create_index("ix_manychat_events_channel", "manychat_events", ["channel"], unique=False)
    op.create_index(
        "ix_manychat_events_org_flow_type",
        "manychat_events",
        ["org_id", "flow_id", "event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_manychat_events_org_flow_type", table_name="manychat_events")
    op.drop_index("ix_manychat_events_channel", table_name="manychat_events")
    op.drop_index("ix_manychat_events_event_type", table_name="manychat_events")
    op.drop_index("ix_manychat_events_flow_id", table_name="manychat_events")
    op.drop_index("ix_manychat_events_manychat_subscriber_id", table_name="manychat_events")
    op.drop_index("ix_manychat_events_org_id", table_name="manychat_events")
    op.drop_table("manychat_events")

