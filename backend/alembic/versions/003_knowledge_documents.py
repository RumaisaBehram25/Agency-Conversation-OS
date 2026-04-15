"""Add knowledge_documents table

Revision ID: 003
Revises: 002
Create Date: 2026-03-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Knowledge Documents ──────────────────────────────────
    op.create_table(
        "knowledge_documents",
        sa.Column("id", UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        # Content
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # Classification
        sa.Column("keywords", ARRAY(sa.Text()), nullable=True),
        sa.Column("source_file", sa.String(255), nullable=True),
        sa.Column("section_name", sa.String(255), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        # Status
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # GIN index on keywords array for efficient array overlap queries
    # (e.g. WHERE keywords && ARRAY['objection', 'pricing'])
    op.create_index(
        "idx_knowledge_documents_keywords",
        "knowledge_documents",
        ["keywords"],
        postgresql_using="gin",
    )

    # Index on category for filtered lookups
    op.create_index(
        "idx_knowledge_documents_category",
        "knowledge_documents",
        ["category"],
    )


def downgrade() -> None:
    op.drop_table("knowledge_documents")
