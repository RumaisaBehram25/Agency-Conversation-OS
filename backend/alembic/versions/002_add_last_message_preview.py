"""Add conversation last_message_preview column

Revision ID: 002_add_last_message_preview
Revises: 001
Create Date: 2026-04-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "002_add_last_message_preview"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("conversations")}
    if "last_message_preview" not in columns:
        op.add_column(
            "conversations",
            sa.Column("last_message_preview", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("conversations")}
    if "last_message_preview" in columns:
        op.drop_column("conversations", "last_message_preview")