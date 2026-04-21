"""Attribute UTM + Attora campaign onto conversion_events

Revision ID: 010_conversion_event_utm
Revises: 009_merge_heads
Create Date: 2026-04-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_conversion_event_utm"
down_revision: Union[str, None] = "009_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversion_events",
        sa.Column("attora_campaign_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "conversion_events",
        sa.Column("utm_source", sa.String(100), nullable=True),
    )
    op.add_column(
        "conversion_events",
        sa.Column("utm_medium", sa.String(100), nullable=True),
    )
    op.add_column(
        "conversion_events",
        sa.Column("utm_campaign", sa.String(255), nullable=True),
    )
    op.add_column(
        "conversion_events",
        sa.Column("utm_content", sa.String(100), nullable=True),
    )
    op.add_column(
        "conversion_events",
        sa.Column("attora_sub", sa.String(255), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversion_events_attora_campaign_id",
        "conversion_events",
        "ad_campaigns",
        ["attora_campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_conversion_events_attora_campaign_id",
        "conversion_events",
        ["attora_campaign_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversion_events_attora_campaign_id", "conversion_events"
    )
    op.drop_constraint(
        "fk_conversion_events_attora_campaign_id",
        "conversion_events",
        type_="foreignkey",
    )
    op.drop_column("conversion_events", "attora_sub")
    op.drop_column("conversion_events", "utm_content")
    op.drop_column("conversion_events", "utm_campaign")
    op.drop_column("conversion_events", "utm_medium")
    op.drop_column("conversion_events", "utm_source")
    op.drop_column("conversion_events", "attora_campaign_id")
