"""Add confirmed buyer stage

Revision ID: 3ce8b94fe540
Revises: 024_wb_escalation_fixes
Create Date: 2026-05-11 22:51:24.109652+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '3ce8b94fe540'
down_revision: Union[str, None] = '024_wb_escalation_fixes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # All operations are idempotent (IF EXISTS / IF NOT EXISTS) to handle partial prior runs

    # ai_config
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE ai_config DROP CONSTRAINT IF EXISTS ai_config_org_id_key;
        EXCEPTION WHEN others THEN null; END $$;
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_config_org_id ON ai_config (org_id);")
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE ai_config ADD CONSTRAINT uq_ai_config_org_id UNIQUE (org_id);
        EXCEPTION WHEN duplicate_table THEN null; END $$;
    """)

    # ai_usage_events
    op.execute("DROP INDEX IF EXISTS idx_ai_usage_events_org_created;")

    # campaign_breakdowns
    op.execute("DROP INDEX IF EXISTS idx_campaign_breakdowns_org_date;")

    # campaign_follow_ups
    op.execute("DROP INDEX IF EXISTS ix_campaign_follow_ups_org;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_campaign_follow_ups_org_id ON campaign_follow_ups (org_id);")

    # campaign_metrics
    op.execute("DROP INDEX IF EXISTS idx_campaign_metrics_org_date;")
    op.execute("DROP INDEX IF EXISTS ix_campaign_metrics_ad_post_lookup;")

    # conversations
    op.execute("DROP INDEX IF EXISTS idx_conversations_activity;")
    op.execute("DROP INDEX IF EXISTS idx_conversations_org;")
    op.execute("DROP INDEX IF EXISTS idx_conversations_status;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_conversations_last_activity_at ON conversations (last_activity_at);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_conversations_org_id ON conversations (org_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_conversations_status ON conversations (status);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_conversations_subscriber_id ON conversations (subscriber_id);")
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE conversations DROP COLUMN IF EXISTS last_message_preview;
        EXCEPTION WHEN others THEN null; END $$;
    """)

    # conversion_events
    op.execute("DROP INDEX IF EXISTS idx_conversions_date;")
    op.execute("DROP INDEX IF EXISTS idx_conversions_org;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_conversion_events_conversation_id ON conversion_events (conversation_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_conversion_events_org_id ON conversion_events (org_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_conversion_events_subscriber_id ON conversion_events (subscriber_id);")

    # daily_analytics
    op.execute("DROP INDEX IF EXISTS idx_analytics_org_date;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daily_analytics_date ON daily_analytics (date);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daily_analytics_org_id ON daily_analytics (org_id);")

    # hyros_sync_logs
    op.execute("DROP INDEX IF EXISTS ix_hyros_sync_logs_org_synced_at;")

    # knowledge_documents
    op.execute("DROP INDEX IF EXISTS idx_knowledge_documents_category;")
    op.execute("DROP INDEX IF EXISTS idx_knowledge_documents_keywords;")

    # messages
    op.execute("DROP INDEX IF EXISTS idx_messages_conversation;")
    op.execute("DROP INDEX IF EXISTS idx_messages_created;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_messages_conversation_id ON messages (conversation_id);")

    # products
    op.execute("DROP INDEX IF EXISTS idx_products_org;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_products_org_id ON products (org_id);")

    # subscribers
    op.execute("DROP INDEX IF EXISTS idx_subscribers_converted;")
    op.execute("DROP INDEX IF EXISTS idx_subscribers_ctwa;")
    op.execute("DROP INDEX IF EXISTS idx_subscribers_org;")
    op.execute("DROP INDEX IF EXISTS idx_subscribers_stage;")
    op.execute("DROP INDEX IF EXISTS ix_subscribers_hyros_email;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscribers_buyer_stage ON subscribers (buyer_stage);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscribers_ctwa_clid ON subscribers (ctwa_clid);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscribers_org_id ON subscribers (org_id);")

    # users
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key;
        EXCEPTION WHEN others THEN null; END $$;
    """)
    op.execute("DROP INDEX IF EXISTS ix_users_email;")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_email;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);")
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email);
        EXCEPTION WHEN duplicate_table THEN null; END $$;
    """)
    op.execute("DROP INDEX IF EXISTS ix_subscribers_org_id;")
    op.execute("DROP INDEX IF EXISTS ix_subscribers_ctwa_clid;")
    op.execute("DROP INDEX IF EXISTS ix_subscribers_buyer_stage;")
    op.execute("CREATE INDEX IF NOT EXISTS idx_subscribers_stage ON subscribers (buyer_stage);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_subscribers_org ON subscribers (org_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_subscribers_ctwa ON subscribers (ctwa_clid);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_subscribers_converted ON subscribers (org_id, is_converted);")
    op.execute("DROP INDEX IF EXISTS ix_products_org_id;")
    op.execute("CREATE INDEX IF NOT EXISTS idx_products_org ON products (org_id);")
    op.execute("DROP INDEX IF EXISTS ix_messages_conversation_id;")
    op.execute("CREATE INDEX IF NOT EXISTS idx_messages_created ON messages (created_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages (conversation_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_documents_category ON knowledge_documents (category);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_hyros_sync_logs_org_synced_at ON hyros_sync_logs (org_id, synced_at);")
    op.execute("DROP INDEX IF EXISTS ix_daily_analytics_org_id;")
    op.execute("DROP INDEX IF EXISTS ix_daily_analytics_date;")
    op.execute("CREATE INDEX IF NOT EXISTS idx_analytics_org_date ON daily_analytics (org_id, date DESC);")
    op.execute("DROP INDEX IF EXISTS ix_conversion_events_subscriber_id;")
    op.execute("DROP INDEX IF EXISTS ix_conversion_events_org_id;")
    op.execute("DROP INDEX IF EXISTS ix_conversion_events_conversation_id;")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversions_org ON conversion_events (org_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversions_date ON conversion_events (created_at DESC);")
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE conversations ADD COLUMN IF NOT EXISTS last_message_preview TEXT;
        EXCEPTION WHEN others THEN null; END $$;
    """)
    op.execute("DROP INDEX IF EXISTS ix_conversations_subscriber_id;")
    op.execute("DROP INDEX IF EXISTS ix_conversations_status;")
    op.execute("DROP INDEX IF EXISTS ix_conversations_org_id;")
    op.execute("DROP INDEX IF EXISTS ix_conversations_last_activity_at;")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations (org_id, status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversations_org ON conversations (org_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversations_activity ON conversations (last_activity_at DESC);")
    op.execute("DROP INDEX IF EXISTS ix_campaign_follow_ups_org_id;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_campaign_follow_ups_org ON campaign_follow_ups (org_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_campaign_breakdowns_org_date ON campaign_breakdowns (org_id, date DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_events_org_created ON ai_usage_events (org_id, created_at DESC);")
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE ai_config DROP CONSTRAINT IF EXISTS uq_ai_config_org_id;
        EXCEPTION WHEN others THEN null; END $$;
    """)
    op.execute("DROP INDEX IF EXISTS ix_ai_config_org_id;")
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE ai_config ADD CONSTRAINT ai_config_org_id_key UNIQUE (org_id);
        EXCEPTION WHEN duplicate_table THEN null; END $$;
    """)