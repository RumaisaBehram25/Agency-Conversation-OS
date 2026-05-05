"""Add follow-up workflow tables and columns

Per-campaign follow-up rules (`campaign_follow_ups`) plus the columns the
dispatcher needs to track silence timing and dedupe sends:

  - subscribers.last_user_message_at — anchor for "how long has the user
    been silent?". Distinct from last_message_at, which gets bumped by
    AI replies too.
  - conversations.follow_up_attempts / last_follow_up_at — counters so the
    dispatcher knows which rule to fire next and avoids double-sending.
  - messages.is_follow_up — distinguishes nudges from organic AI replies
    in dashboards and exports.
  - organizations.manychat_outbound_flow_ns — the namespace of the "open"
    ManyChat flow that takes (subscriber_id, message_text) and just sends
    it. Per-org because each org wires this up in their own ManyChat.

Revision ID: 020_follow_up_workflow
Revises: 019_campaign_conversation_script
Create Date: 2026-05-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "020_follow_up_workflow"
down_revision: Union[str, None] = "019_campaign_conversation_script"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # campaign_follow_ups — one row per touch in the sequence.
    op.create_table(
        "campaign_follow_ups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            sa.Uuid(),
            sa.ForeignKey("ad_campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("after_minutes", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_final", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
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
    op.create_index(
        "uq_campaign_follow_ups_step",
        "campaign_follow_ups",
        ["campaign_id", "step_order"],
        unique=True,
    )
    op.create_index(
        "ix_campaign_follow_ups_org",
        "campaign_follow_ups",
        ["org_id"],
    )

    # subscribers.last_user_message_at — silence anchor.
    op.add_column(
        "subscribers",
        sa.Column(
            "last_user_message_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_subscribers_last_user_message_at",
        "subscribers",
        ["last_user_message_at"],
    )

    # conversations follow-up tracking.
    op.add_column(
        "conversations",
        sa.Column(
            "follow_up_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "last_follow_up_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # messages.is_follow_up flag.
    op.add_column(
        "messages",
        sa.Column(
            "is_follow_up",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )

    # organizations.manychat_outbound_flow_ns — namespace of the dumb
    # "send-this-text" ManyChat flow.
    op.add_column(
        "organizations",
        sa.Column(
            "manychat_outbound_flow_ns",
            sa.String(length=255),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "manychat_outbound_flow_ns")
    op.drop_column("messages", "is_follow_up")
    op.drop_column("conversations", "last_follow_up_at")
    op.drop_column("conversations", "follow_up_attempts")
    op.drop_index("ix_subscribers_last_user_message_at", table_name="subscribers")
    op.drop_column("subscribers", "last_user_message_at")
    op.drop_index("ix_campaign_follow_ups_org", table_name="campaign_follow_ups")
    op.drop_index("uq_campaign_follow_ups_step", table_name="campaign_follow_ups")
    op.drop_table("campaign_follow_ups")
