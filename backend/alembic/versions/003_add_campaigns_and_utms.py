"""Add ad_campaigns, campaign_utms tables and subscriber attora_campaign_id

Revision ID: 003_add_campaigns_and_utms
Revises: 002_add_last_message_preview
Create Date: 2026-04-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_add_campaigns_and_utms"
down_revision: Union[str, None] = "002_add_last_message_preview"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ad_campaigns ─────────────────────────────────────────
    op.create_table(
        "ad_campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("meta_campaign_id", sa.String(255), nullable=True),
        sa.Column("meta_ad_set_id", sa.String(255), nullable=True),
        sa.Column("is_attora_managed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ad_campaigns_org_id", "ad_campaigns", ["org_id"])
    op.create_index("ix_ad_campaigns_meta_campaign_id", "ad_campaigns", ["meta_campaign_id"])

    # ── campaign_utms ─────────────────────────────────────────
    op.create_table(
        "campaign_utms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("utm_source", sa.String(100), nullable=False, server_default="attora"),
        sa.Column("utm_medium", sa.String(100), nullable=False, server_default="messaging"),
        sa.Column("utm_campaign", sa.String(255), nullable=False),
        sa.Column("product_page_url", sa.Text(), nullable=True),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("success_url", sa.Text(), nullable=True),
        sa.Column("product_page_utm_url", sa.Text(), nullable=True),
        sa.Column("checkout_utm_url", sa.Text(), nullable=True),
        sa.Column("success_utm_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["ad_campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", name="uq_campaign_utms_campaign_id"),
        sa.UniqueConstraint("org_id", "campaign_id", name="uq_campaign_utms_org_campaign"),
    )
    op.create_index("ix_campaign_utms_org_id", "campaign_utms", ["org_id"])

    # ── subscribers: add attora_campaign_id FK ────────────────
    op.add_column(
        "subscribers",
        sa.Column("attora_campaign_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_subscribers_attora_campaign_id",
        "subscribers",
        "ad_campaigns",
        ["attora_campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_subscribers_attora_campaign_id", "subscribers", ["attora_campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_subscribers_attora_campaign_id", "subscribers")
    op.drop_constraint("fk_subscribers_attora_campaign_id", "subscribers", type_="foreignkey")
    op.drop_column("subscribers", "attora_campaign_id")

    op.drop_index("ix_campaign_utms_org_id", "campaign_utms")
    op.drop_table("campaign_utms")

    op.drop_index("ix_ad_campaigns_meta_campaign_id", "ad_campaigns")
    op.drop_index("ix_ad_campaigns_org_id", "ad_campaigns")
    op.drop_table("ad_campaigns")
