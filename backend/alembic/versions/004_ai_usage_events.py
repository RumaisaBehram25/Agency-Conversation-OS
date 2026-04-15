"""Add ai_usage_events table

Revision ID: 004
Revises: 003
Create Date: 2026-04-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_events",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "org_id",
            UUID(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            UUID(),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "message_id",
            UUID(),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
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


def downgrade() -> None:
    op.drop_table("ai_usage_events")
