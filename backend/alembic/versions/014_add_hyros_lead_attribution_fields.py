"""Add richer Hyros lead attribution fields to subscribers

Revision ID: 014_add_hyros_lead_attribution_fields
Revises: 013_add_hyros_fields
Create Date: 2026-04-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014_hyros_attribution"
down_revision: Union[str, None] = "013_add_hyros_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscribers",
        sa.Column("hyros_lead_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "subscribers",
        sa.Column("hyros_email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "subscribers",
        sa.Column("hyros_origin_source", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "subscribers",
        sa.Column("hyros_origin_tag", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "subscribers",
        sa.Column("hyros_traffic_source", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "subscribers",
        sa.Column("hyros_creative_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "subscribers",
        sa.Column("hyros_purchase_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_subscribers_hyros_lead_id",
        "subscribers",
        ["hyros_lead_id"],
    )
    op.create_index(
        "ix_subscribers_hyros_email",
        "subscribers",
        ["hyros_email"],
    )


def downgrade() -> None:
    op.drop_index("ix_subscribers_hyros_email", table_name="subscribers")
    op.drop_index("ix_subscribers_hyros_lead_id", table_name="subscribers")
    op.drop_column("subscribers", "hyros_purchase_date")
    op.drop_column("subscribers", "hyros_creative_name")
    op.drop_column("subscribers", "hyros_traffic_source")
    op.drop_column("subscribers", "hyros_origin_tag")
    op.drop_column("subscribers", "hyros_origin_source")
    op.drop_column("subscribers", "hyros_email")
    op.drop_column("subscribers", "hyros_lead_id")
