"""Add conversation last_message_preview column

Revision ID: 002
Revises: 001
Create Date: 2026-04-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("last_message_preview", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "last_message_preview")