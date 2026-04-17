"""Add post_id column to campaign_metrics

Revision ID: 008
Revises: 007
Create Date: 2026-04-16

Caches the Meta ad creative's effective_object_story_id ({page_id}_{post_id})
on level='ad' rows, so we can resolve subscribers.post_id from subscribers.ad_id
without hitting the Meta Graph API at ingest time.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEX_NAME = "ix_campaign_metrics_ad_post_lookup"


def upgrade() -> None:
    op.add_column(
        "campaign_metrics",
        sa.Column("post_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        _INDEX_NAME,
        "campaign_metrics",
        ["meta_ad_id"],
        unique=False,
        postgresql_where=sa.text("level = 'ad' AND post_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="campaign_metrics")
    op.drop_column("campaign_metrics", "post_id")
