"""Idempotently repair schema drift from the 002_campaign_metrics branch.

Revision ID: 011_repair_missing_schema
Revises: 010_conversion_event_utm
Create Date: 2026-04-21

Some environments had alembic_version stamped forward past the
002_campaign_metrics → 008 branch without its DDL actually executing (the
other branch, 002_add_last_message_preview → 003_add_campaigns_and_utms,
did run and merged via 009). This migration re-applies the missing DDL
idempotently so those environments converge with fresh-install environments.

On a clean DB where 002 through 008 ran correctly, every check below is a
no-op.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "011_repair_missing_schema"
down_revision: Union[str, None] = "010_conversion_event_utm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return column in {c["name"] for c in _inspector().get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    if not _has_table(table):
        return False
    return name in {ix["name"] for ix in _inspector().get_indexes(table)}


def upgrade() -> None:
    # ── 002: campaign_metrics + campaign_breakdowns ───────────
    if not _has_table("campaign_metrics"):
        op.create_table(
            "campaign_metrics",
            sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("org_id", UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("level", sa.String(20), nullable=False),
            sa.Column("meta_campaign_id", sa.String(255), nullable=True),
            sa.Column("meta_campaign_name", sa.String(255), nullable=True),
            sa.Column("meta_adset_id", sa.String(255), nullable=True),
            sa.Column("meta_adset_name", sa.String(255), nullable=True),
            sa.Column("meta_ad_id", sa.String(255), nullable=True),
            sa.Column("meta_ad_name", sa.String(255), nullable=True),
            sa.Column("status", sa.String(50), nullable=True),
            sa.Column("objective", sa.String(100), nullable=True),
            sa.Column("daily_budget", sa.Numeric(10, 2), nullable=True),
            sa.Column("spend", sa.Numeric(10, 2), nullable=False),
            sa.Column("impressions", sa.Integer(), server_default="0", nullable=False),
            sa.Column("clicks", sa.Integer(), server_default="0", nullable=False),
            sa.Column("reach", sa.Integer(), server_default="0", nullable=False),
            sa.Column("frequency", sa.Numeric(5, 2), nullable=True),
            sa.Column("cpc", sa.Numeric(10, 4), nullable=True),
            sa.Column("cpm", sa.Numeric(10, 4), nullable=True),
            sa.Column("ctr", sa.Numeric(5, 4), nullable=True),
            sa.Column("leads", sa.Integer(), server_default="0", nullable=False),
            sa.Column("cost_per_lead", sa.Numeric(10, 2), nullable=True),
            sa.Column("link_clicks", sa.Integer(), server_default="0", nullable=False),
            sa.Column("landing_page_views", sa.Integer(), server_default="0", nullable=False),
            sa.Column("video_views", sa.Integer(), server_default="0", nullable=False),
            sa.Column("post_engagement", sa.Integer(), server_default="0", nullable=False),
            sa.Column("messaging_conversations_started", sa.Integer(), server_default="0", nullable=False),
            sa.Column("messaging_first_reply", sa.Integer(), server_default="0", nullable=False),
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
        op.create_index(
            "idx_campaign_metrics_org_date",
            "campaign_metrics",
            ["org_id", "date"],
            postgresql_ops={"date": "DESC"},
        )

    if not _has_table("campaign_breakdowns"):
        op.create_table(
            "campaign_breakdowns",
            sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("org_id", UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("meta_campaign_id", sa.String(255), nullable=True),
            sa.Column("meta_adset_id", sa.String(255), nullable=True),
            sa.Column("meta_ad_id", sa.String(255), nullable=True),
            sa.Column("breakdown_type", sa.String(50), nullable=False),
            sa.Column("breakdown_key", sa.String(100), nullable=False),
            sa.Column("spend", sa.Numeric(10, 2), server_default="0", nullable=False),
            sa.Column("impressions", sa.Integer(), server_default="0", nullable=False),
            sa.Column("clicks", sa.Integer(), server_default="0", nullable=False),
            sa.Column("leads", sa.Integer(), server_default="0", nullable=False),
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
        op.create_index(
            "idx_campaign_breakdowns_org_date",
            "campaign_breakdowns",
            ["org_id", "date"],
            postgresql_ops={"date": "DESC"},
        )

    # ── 003: knowledge_documents ──────────────────────────────
    if not _has_table("knowledge_documents"):
        op.create_table(
            "knowledge_documents",
            sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("keywords", ARRAY(sa.Text()), nullable=True),
            sa.Column("source_file", sa.String(255), nullable=True),
            sa.Column("section_name", sa.String(255), nullable=True),
            sa.Column("category", sa.String(100), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(
            "idx_knowledge_documents_keywords",
            "knowledge_documents",
            ["keywords"],
            postgresql_using="gin",
        )
        op.create_index(
            "idx_knowledge_documents_category",
            "knowledge_documents",
            ["category"],
        )

    # ── 004: ai_usage_events ──────────────────────────────────
    if not _has_table("ai_usage_events"):
        op.create_table(
            "ai_usage_events",
            sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("org_id", UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("conversation_id", UUID(), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("message_id", UUID(), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
            sa.Column("stage", sa.String(32), nullable=False),
            sa.Column("model", sa.String(100), nullable=False),
            sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
            sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
            sa.Column("cache_read_tokens", sa.Integer(), server_default="0", nullable=False),
            sa.Column("cache_creation_tokens", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_ai_usage_events_org_id", "ai_usage_events", ["org_id"])
        op.create_index("ix_ai_usage_events_conversation_id", "ai_usage_events", ["conversation_id"])
        op.create_index("ix_ai_usage_events_stage", "ai_usage_events", ["stage"])
        op.create_index("ix_ai_usage_events_model", "ai_usage_events", ["model"])
        op.create_index(
            "idx_ai_usage_events_org_created",
            "ai_usage_events",
            ["org_id", "created_at"],
            postgresql_ops={"created_at": "DESC"},
        )

    # ── 005: subscribers.history ──────────────────────────────
    if not _has_column("subscribers", "history"):
        op.add_column("subscribers", sa.Column("history", JSONB(), nullable=True))

    # ── 006: ai_config.conversion_playbook -> JSONB ───────────
    if _has_table("ai_config"):
        cols = {c["name"]: c for c in _inspector().get_columns("ai_config")}
        playbook = cols.get("conversion_playbook")
        if playbook is not None and not isinstance(playbook["type"], sa.dialects.postgresql.JSONB):
            # Only convert if it's still TEXT-ish. Wipe existing text (old migration does this too).
            type_str = str(playbook["type"]).upper()
            if "JSON" not in type_str:
                op.alter_column(
                    "ai_config",
                    "conversion_playbook",
                    existing_type=sa.Text(),
                    type_=JSONB(),
                    existing_nullable=True,
                    postgresql_using="NULL",
                )

    # ── 007: subscribers.post_id ──────────────────────────────
    if not _has_column("subscribers", "post_id"):
        op.add_column(
            "subscribers",
            sa.Column("post_id", sa.String(length=255), nullable=True),
        )

    # ── 008: campaign_metrics.post_id + partial index ─────────
    if _has_table("campaign_metrics"):
        if not _has_column("campaign_metrics", "post_id"):
            op.add_column(
                "campaign_metrics",
                sa.Column("post_id", sa.String(length=255), nullable=True),
            )
        if not _has_index("campaign_metrics", "ix_campaign_metrics_ad_post_lookup"):
            op.create_index(
                "ix_campaign_metrics_ad_post_lookup",
                "campaign_metrics",
                ["meta_ad_id"],
                unique=False,
                postgresql_where=sa.text("level = 'ad' AND post_id IS NOT NULL"),
            )


def downgrade() -> None:
    # This is a repair migration — we don't know which pieces it actually
    # created vs. which were already there. Safest downgrade is a no-op.
    pass
