"""Add history column to subscribers

Revision ID: 005
Revises: 004
Create Date: 2026-04-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscribers",
        sa.Column("history", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscribers", "history")
