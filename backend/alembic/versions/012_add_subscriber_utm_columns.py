"""Add UTM attribution columns to subscribers

Revision ID: 012_add_subscriber_utm
Revises: 011_repair_missing_schema
Create Date: 2026-04-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_add_subscriber_utm"
down_revision: Union[str, None] = "011_repair_missing_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscribers",
        sa.Column("utm_source", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "subscribers",
        sa.Column("utm_medium", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "subscribers",
        sa.Column("utm_campaign", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "subscribers",
        sa.Column("utm_content", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscribers", "utm_content")
    op.drop_column("subscribers", "utm_campaign")
    op.drop_column("subscribers", "utm_medium")
    op.drop_column("subscribers", "utm_source")
