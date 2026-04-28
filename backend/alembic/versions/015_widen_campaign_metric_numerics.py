"""Widen campaign_metrics numeric columns to match model

Migration 002 created `frequency` as NUMERIC(5, 2) and `ctr` as NUMERIC(5, 4),
but the SQLAlchemy model declares both as Numeric(10, 4). Real Meta data
overflows the narrower DB columns — a CTR of 10%+ raises NumericValueOutOfRange
on insert, silently breaking every granular sync. This migration widens the
columns to match the model.

Revision ID: 015_widen_metric_nums
Revises: 014_hyros_attribution
Create Date: 2026-04-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "015_widen_metric_nums"
down_revision: Union[str, None] = "014_hyros_attribution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "campaign_metrics",
        "frequency",
        existing_type=sa.Numeric(5, 2),
        type_=sa.Numeric(10, 4),
        existing_nullable=True,
    )
    op.alter_column(
        "campaign_metrics",
        "ctr",
        existing_type=sa.Numeric(5, 4),
        type_=sa.Numeric(10, 4),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "campaign_metrics",
        "ctr",
        existing_type=sa.Numeric(10, 4),
        type_=sa.Numeric(5, 4),
        existing_nullable=True,
    )
    op.alter_column(
        "campaign_metrics",
        "frequency",
        existing_type=sa.Numeric(10, 4),
        type_=sa.Numeric(5, 2),
        existing_nullable=True,
    )
