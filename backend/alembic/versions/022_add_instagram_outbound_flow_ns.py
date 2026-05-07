"""Add ManyChat Instagram outbound flow namespace on organizations

Revision ID: 022_instagram_outbound_flow_ns
Revises: 021_hyros_sync_logs
Create Date: 2026-05-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "022_instagram_outbound_flow_ns"
down_revision: Union[str, None] = "021_hyros_sync_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "manychat_outbound_flow_ns_instagram",
            sa.String(length=255),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "manychat_outbound_flow_ns_instagram")
