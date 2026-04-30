"""Add keyword + source_type to ad_campaigns

Adds two columns to support keyword-based attribution for organic posts:
- source_type: 'paid' | 'organic' — explicit channel marker (was inferred
  from meta_campaign_id null-ness)
- keyword: ManyChat trigger word that routes a lead to this campaign on
  subscriber upsert (e.g. 'MUSCLE', 'MACROS')

Backfill: existing rows with meta_campaign_id IS NULL → 'organic',
otherwise 'paid'. Partial unique index on (org_id, keyword) WHERE keyword
IS NOT NULL prevents duplicate keywords per org without colliding on NULL
for paid campaigns that don't use one.

Revision ID: 017_keyword_source_type
Revises: 016_manychat_events
Create Date: 2026-04-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "017_keyword_source_type"
down_revision: Union[str, None] = "016_manychat_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ad_campaigns",
        sa.Column(
            "source_type",
            sa.String(length=20),
            nullable=False,
            server_default="paid",
        ),
    )
    op.add_column(
        "ad_campaigns",
        sa.Column("keyword", sa.String(length=100), nullable=True),
    )

    # Backfill organic source_type for campaigns without a Meta ID.
    op.execute(
        "UPDATE ad_campaigns "
        "SET source_type = 'organic' "
        "WHERE meta_campaign_id IS NULL"
    )

    # Drop server_default now that the backfill is done — model uses python-side default.
    op.alter_column("ad_campaigns", "source_type", server_default=None)

    op.create_index(
        "ix_ad_campaigns_source_type",
        "ad_campaigns",
        ["source_type"],
    )
    op.create_index(
        "ix_ad_campaigns_keyword",
        "ad_campaigns",
        ["keyword"],
    )
    op.create_index(
        "uq_ad_campaigns_org_keyword",
        "ad_campaigns",
        ["org_id", "keyword"],
        unique=True,
        postgresql_where=sa.text("keyword IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_ad_campaigns_org_keyword", table_name="ad_campaigns")
    op.drop_index("ix_ad_campaigns_keyword", table_name="ad_campaigns")
    op.drop_index("ix_ad_campaigns_source_type", table_name="ad_campaigns")
    op.drop_column("ad_campaigns", "keyword")
    op.drop_column("ad_campaigns", "source_type")
