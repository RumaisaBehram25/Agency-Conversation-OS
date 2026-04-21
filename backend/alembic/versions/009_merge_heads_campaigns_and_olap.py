"""Merge campaign/UTM branch with analytics/OLAP branch.

Revision ID: 009_merge_heads
Revises: 008, 003_add_campaigns_and_utms
Create Date: 2026-04-21
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "009_merge_heads"
down_revision: Union[str, Sequence[str], None] = ("008", "003_add_campaigns_and_utms")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
