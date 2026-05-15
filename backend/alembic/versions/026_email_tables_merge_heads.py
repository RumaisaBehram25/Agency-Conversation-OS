"""Email settings, log, and queue tables

Revision ID: 026_email_tables
Revises: 025_wb_ask_before_link, 3ce8b94fe540
Create Date: 2026-05-15

Merges the two Alembic heads (!025_wb_ask_before_link, 3ce8b94fe540) and adds
PostgreSQL tables for outbound email configuration, delivery history, and a
queued-sends backlog (matching the application's email helpers).
"""

from typing import Sequence, Tuple, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "026_email_tables"
down_revision: Union[str, Tuple[str, ...], None] = (
    "025_wb_ask_before_link",
    "3ce8b94fe540",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_email_settings",
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "emails_enabled",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "blocked_product_ids",
            JSONB(astext_type=sa.Text()),
            server_default=text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "max_emails_per_user_per_month",
            sa.Integer(),
            server_default="4",
            nullable=False,
        ),
        sa.Column(
            "min_days_between_emails",
            sa.Integer(),
            server_default="7",
            nullable=False,
        ),
        sa.Column(
            "no_response_followup_days",
            sa.Integer(),
            server_default="30",
            nullable=False,
        ),
        sa.Column("from_name", sa.Text(), nullable=True),
        sa.Column("from_email", sa.Text(), nullable=True),
        sa.Column("reply_to", sa.Text(), nullable=True),
        sa.Column("resend_api_key", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "email_log",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscriber_id",
            UUID(as_uuid=True),
            sa.ForeignKey("subscribers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("suppression_reason", sa.Text(), nullable=True),
        sa.Column("resend_message_id", sa.Text(), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_email_log_org_subscriber",
        "email_log",
        ["organization_id", "subscriber_id"],
        unique=False,
    )

    op.create_table(
        "email_queue",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("subscriber_id", sa.UUID(), nullable=False),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=True),
        sa.Column("campaign_id", sa.UUID(), nullable=True),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column(
            "scheduled_for",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"]),
    )
    op.create_index(
        "idx_email_queue_pending",
        "email_queue",
        ["organization_id", "scheduled_for"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_email_queue_pending;")
    op.drop_table("email_queue")

    op.drop_index("ix_email_log_org_subscriber", table_name="email_log")
    op.drop_table("email_log")

    op.drop_table("organization_email_settings")
