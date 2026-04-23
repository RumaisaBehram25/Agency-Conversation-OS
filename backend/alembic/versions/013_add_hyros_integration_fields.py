"""Add Hyros integration fields for org settings and subscriber status

Revision ID: 013_add_hyros_fields
Revises: 012_add_subscriber_utm
Create Date: 2026-04-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_add_hyros_fields"
down_revision: Union[str, None] = "012_add_subscriber_utm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("hyros_api_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "subscribers",
        sa.Column("hyros_purchased", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "subscribers",
        sa.Column("hyros_product", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "subscribers",
        sa.Column("hyros_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("ad_name", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_documents", "ad_name")
    op.drop_column("subscribers", "hyros_synced_at")
    op.drop_column("subscribers", "hyros_product")
    op.drop_column("subscribers", "hyros_purchased")
    op.drop_column("organizations", "hyros_api_key")
