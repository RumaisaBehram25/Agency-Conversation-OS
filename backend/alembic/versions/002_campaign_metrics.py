"""Add campaign_metrics and campaign_breakdowns tables

Revision ID: 002
Revises: 001
Create Date: 2026-03-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Campaign Metrics ──────────────────────────────────────
    op.create_table(
        "campaign_metrics",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        # Meta entity IDs
        sa.Column("meta_campaign_id", sa.String(255), nullable=True),
        sa.Column("meta_campaign_name", sa.String(255), nullable=True),
        sa.Column("meta_adset_id", sa.String(255), nullable=True),
        sa.Column("meta_adset_name", sa.String(255), nullable=True),
        sa.Column("meta_ad_id", sa.String(255), nullable=True),
        sa.Column("meta_ad_name", sa.String(255), nullable=True),
        # Campaign config
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("objective", sa.String(100), nullable=True),
        sa.Column("daily_budget", sa.Numeric(10, 2), nullable=True),
        # Core metrics
        sa.Column("spend", sa.Numeric(10, 2), nullable=False),
        sa.Column("impressions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("clicks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reach", sa.Integer(), server_default="0", nullable=False),
        sa.Column("frequency", sa.Numeric(5, 2), nullable=True),
        sa.Column("cpc", sa.Numeric(10, 4), nullable=True),
        sa.Column("cpm", sa.Numeric(10, 4), nullable=True),
        sa.Column("ctr", sa.Numeric(5, 4), nullable=True),
        # Conversion metrics
        sa.Column("leads", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_per_lead", sa.Numeric(10, 2), nullable=True),
        # Engagement metrics
        sa.Column("link_clicks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("landing_page_views", sa.Integer(), server_default="0", nullable=False),
        sa.Column("video_views", sa.Integer(), server_default="0", nullable=False),
        sa.Column("post_engagement", sa.Integer(), server_default="0", nullable=False),
        # Messaging metrics
        sa.Column("messaging_conversations_started", sa.Integer(), server_default="0", nullable=False),
        sa.Column("messaging_first_reply", sa.Integer(), server_default="0", nullable=False),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "org_id", "date", "level",
            "meta_campaign_id", "meta_adset_id", "meta_ad_id",
            name="uq_campaign_metrics_org_date_entity",
        ),
    )
    op.create_index("ix_campaign_metrics_org_id", "campaign_metrics", ["org_id"])
    op.create_index("ix_campaign_metrics_date", "campaign_metrics", ["date"])
    op.create_index("idx_campaign_metrics_org_date", "campaign_metrics", ["org_id", "date"], postgresql_ops={"date": "DESC"})

    # ── Campaign Breakdowns ───────────────────────────────────
    op.create_table(
        "campaign_breakdowns",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        # Meta entity IDs
        sa.Column("meta_campaign_id", sa.String(255), nullable=True),
        sa.Column("meta_adset_id", sa.String(255), nullable=True),
        sa.Column("meta_ad_id", sa.String(255), nullable=True),
        # Breakdown
        sa.Column("breakdown_type", sa.String(50), nullable=False),
        sa.Column("breakdown_key", sa.String(100), nullable=False),
        # Metrics
        sa.Column("spend", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("impressions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("clicks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("leads", sa.Integer(), server_default="0", nullable=False),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "org_id", "date",
            "meta_campaign_id", "meta_adset_id", "meta_ad_id",
            "breakdown_type", "breakdown_key",
            name="uq_campaign_breakdowns_org_date_entity_breakdown",
        ),
    )
    op.create_index("ix_campaign_breakdowns_org_id", "campaign_breakdowns", ["org_id"])
    op.create_index("ix_campaign_breakdowns_date", "campaign_breakdowns", ["date"])
    op.create_index("idx_campaign_breakdowns_org_date", "campaign_breakdowns", ["org_id", "date"], postgresql_ops={"date": "DESC"})


def downgrade() -> None:
    op.drop_table("campaign_breakdowns")
    op.drop_table("campaign_metrics")
