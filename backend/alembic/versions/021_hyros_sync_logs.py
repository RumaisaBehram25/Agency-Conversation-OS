"""Hyros sync audit log for match quality visibility

Revision ID: 021_hyros_sync_logs
Revises: 020_follow_up_workflow
Create Date: 2026-05-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "021_hyros_sync_logs"
down_revision: Union[str, None] = "020_follow_up_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hyros_sync_logs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sales_scanned", sa.Integer(), nullable=False),
        sa.Column("purchases_matched", sa.Integer(), nullable=False),
        sa.Column("unmatched_sales", sa.Integer(), nullable=False),
        sa.Column("matched_by_attora_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_by_attora_sub", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_by_email", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_hyros_sync_logs_org_id",
        "hyros_sync_logs",
        ["org_id"],
    )
    op.create_index(
        "ix_hyros_sync_logs_org_synced_at",
        "hyros_sync_logs",
        ["org_id", "synced_at"],
    )
    op.create_index(
        "ix_hyros_sync_logs_synced_at",
        "hyros_sync_logs",
        ["synced_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_hyros_sync_logs_synced_at", table_name="hyros_sync_logs")
    op.drop_index("ix_hyros_sync_logs_org_synced_at", table_name="hyros_sync_logs")
    op.drop_index("ix_hyros_sync_logs_org_id", table_name="hyros_sync_logs")
    op.drop_table("hyros_sync_logs")
