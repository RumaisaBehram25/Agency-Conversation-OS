"""Initial schema — all MVP tables

Revision ID: 001
Revises: None
Create Date: 2026-03-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Create Enums ─────────────────────────────────────────
    buyer_stage_enum = sa.Enum(
        "awareness", "consideration", "intent", "purchase", "post_purchase",
        name="buyer_stage",
    )
    buyer_stage_enum.create(op.get_bind(), checkfirst=True)

    conversation_status_enum = sa.Enum(
        "active", "converted", "stale", "closed",
        name="conversation_status",
    )
    conversation_status_enum.create(op.get_bind(), checkfirst=True)

    message_sender_enum = sa.Enum(
        "user", "ai", "human",
        name="message_sender",
    )
    message_sender_enum.create(op.get_bind(), checkfirst=True)

    channel_type_enum = sa.Enum(
        "whatsapp", "messenger", "instagram",
        name="channel_type",
    )
    channel_type_enum.create(op.get_bind(), checkfirst=True)

    conversion_type_enum = sa.Enum(
        "lead", "initiate_checkout", "purchase", "upsell",
        name="conversion_type",
    )
    conversion_type_enum.create(op.get_bind(), checkfirst=True)

    user_role_enum = sa.Enum(
        "owner", "admin", "member", "viewer",
        name="user_role",
    )
    user_role_enum.create(op.get_bind(), checkfirst=True)

    # ── Organizations ────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), unique=True, nullable=False),
        # ManyChat config
        sa.Column("manychat_api_key", sa.Text(), nullable=True),
        sa.Column("manychat_page_id", sa.String(255), nullable=True),
        sa.Column("manychat_account_id", sa.String(255), nullable=True),
        # Meta config
        sa.Column("meta_pixel_id", sa.String(255), nullable=True),
        sa.Column("meta_capi_token", sa.Text(), nullable=True),
        sa.Column("meta_ad_account_id", sa.String(255), nullable=True),
        sa.Column("meta_page_id", sa.String(255), nullable=True),
        sa.Column("meta_business_manager_id", sa.String(255), nullable=True),
        # Attora API key
        sa.Column("attora_api_key", sa.Text(), unique=True, nullable=False),
        # Plan
        sa.Column("plan", sa.String(50), server_default="starter", nullable=False),
        sa.Column("monthly_conversation_limit", sa.Integer(), server_default="1000", nullable=False),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Users ────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ── Org Users ────────────────────────────────────────────
    op.create_table(
        "org_users",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", user_role_enum, server_default="member", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "org_id", name="uq_org_users_user_org"),
    )
    op.create_index("ix_org_users_user_id", "org_users", ["user_id"])
    op.create_index("ix_org_users_org_id", "org_users", ["org_id"])

    # ── Products ─────────────────────────────────────────────
    op.create_table(
        "products",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(10), server_default="USD", nullable=False),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("conversion_value", sa.Numeric(10, 2), nullable=True),
        sa.Column("eligibility_criteria", JSONB(), nullable=True),
        sa.Column("objection_responses", JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_products_org", "products", ["org_id"])

    # ── AI Config ────────────────────────────────────────────
    op.create_table(
        "ai_config",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("brand_voice", sa.Text(), nullable=True),
        sa.Column("persona_name", sa.Text(), nullable=True),
        sa.Column("system_prompt_override", sa.Text(), nullable=True),
        sa.Column("product_knowledge", sa.Text(), nullable=True),
        sa.Column("compliance_rules", sa.Text(), nullable=True),
        sa.Column("conversion_playbook", sa.Text(), nullable=True),
        sa.Column("objection_handlers", JSONB(), nullable=True),
        sa.Column("greeting_message", sa.Text(), nullable=True),
        sa.Column("fallback_message", sa.Text(), nullable=True),
        sa.Column("max_messages_before_handoff", sa.Integer(), server_default="50", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        comment="One AI config per organization",
    )

    # ── Subscribers ──────────────────────────────────────────
    op.create_table(
        "subscribers",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manychat_subscriber_id", sa.String(255), nullable=False),
        sa.Column("channel", channel_type_enum, nullable=False),
        # Identity
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        # Attribution
        sa.Column("ctwa_clid", sa.String(255), nullable=True),
        sa.Column("ad_id", sa.String(255), nullable=True),
        sa.Column("ad_set_id", sa.String(255), nullable=True),
        sa.Column("campaign_id", sa.String(255), nullable=True),
        # AI Context
        sa.Column("buyer_stage", buyer_stage_enum, server_default="awareness", nullable=False),
        sa.Column("interests", ARRAY(sa.Text()), nullable=True),
        sa.Column("objections_raised", ARRAY(sa.Text()), nullable=True),
        sa.Column("conversation_summary", sa.Text(), nullable=True),
        # Status
        sa.Column("is_converted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("conversion_value", sa.Numeric(10, 2), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        # Metadata
        sa.Column("first_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_messages", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("org_id", "manychat_subscriber_id", name="uq_subscribers_org_manychat"),
    )
    op.create_index("idx_subscribers_org", "subscribers", ["org_id"])
    op.create_index("idx_subscribers_stage", "subscribers", ["buyer_stage"])
    op.create_index("idx_subscribers_ctwa", "subscribers", ["ctwa_clid"])
    op.create_index("idx_subscribers_converted", "subscribers", ["org_id", "is_converted"])

    # ── Conversations ────────────────────────────────────────
    op.create_table(
        "conversations",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscriber_id", UUID(), sa.ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", channel_type_enum, nullable=False),
        sa.Column("status", conversation_status_enum, server_default="active", nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ai_response_time_avg_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_conversations_org", "conversations", ["org_id"])
    op.create_index("idx_conversations_status", "conversations", ["org_id", "status"])
    op.create_index("idx_conversations_activity", "conversations", ["last_activity_at"], postgresql_ops={"last_activity_at": "DESC"})

    # ── Messages ─────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", UUID(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender", message_sender_enum, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # AI metadata
        sa.Column("intent_signals", ARRAY(sa.Text()), nullable=True),
        sa.Column("buyer_stage_at_time", buyer_stage_enum, nullable=True),
        sa.Column("compliance_flags", ARRAY(sa.Text()), nullable=True),
        sa.Column("ai_model", sa.String(100), nullable=True),
        sa.Column("ai_response_time_ms", sa.Integer(), nullable=True),
        sa.Column("ai_tokens_used", sa.Integer(), nullable=True),
        sa.Column("quick_replies", ARRAY(sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_messages_conversation", "messages", ["conversation_id"])
    op.create_index("idx_messages_created", "messages", ["created_at"], postgresql_ops={"created_at": "DESC"})

    # ── Conversion Events ────────────────────────────────────
    op.create_table(
        "conversion_events",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscriber_id", UUID(), sa.ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", UUID(), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("conversion_type", conversion_type_enum, nullable=False),
        sa.Column("value", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(10), server_default="USD", nullable=False),
        sa.Column("ctwa_clid", sa.String(255), nullable=True),
        sa.Column("capi_event_sent", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("capi_event_id", sa.String(255), nullable=True),
        sa.Column("capi_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta_ad_id", sa.String(255), nullable=True),
        sa.Column("meta_campaign_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_conversions_org", "conversion_events", ["org_id"])
    op.create_index("idx_conversions_date", "conversion_events", ["created_at"], postgresql_ops={"created_at": "DESC"})

    # ── Daily Analytics ──────────────────────────────────────
    op.create_table(
        "daily_analytics",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("channel", channel_type_enum, nullable=True),
        # Conversation metrics
        sa.Column("new_conversations", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active_conversations", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_messages", sa.Integer(), server_default="0", nullable=False),
        sa.Column("avg_messages_per_conversation", sa.Numeric(5, 2), nullable=True),
        sa.Column("avg_ai_response_time_ms", sa.Integer(), nullable=True),
        # Conversion metrics
        sa.Column("conversions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("conversion_value", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("conversion_rate", sa.Numeric(5, 4), nullable=True),
        # Cost metrics
        sa.Column("ad_spend", sa.Numeric(10, 2), nullable=True),
        sa.Column("cpa", sa.Numeric(10, 2), nullable=True),
        sa.Column("roas", sa.Numeric(5, 2), nullable=True),
        # AI metrics
        sa.Column("ai_tokens_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ai_cost", sa.Numeric(10, 4), server_default="0", nullable=False),
        sa.Column("fallback_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("org_id", "date", "channel", name="uq_daily_analytics_org_date_channel"),
    )
    op.create_index("idx_analytics_org_date", "daily_analytics", ["org_id", "date"], postgresql_ops={"date": "DESC"})


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("daily_analytics")
    op.drop_table("conversion_events")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("subscribers")
    op.drop_table("ai_config")
    op.drop_table("products")
    op.drop_table("org_users")
    op.drop_table("users")
    op.drop_table("organizations")

    # Drop enums
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="conversion_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="channel_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="message_sender").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="conversation_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="buyer_stage").drop(op.get_bind(), checkfirst=True)
