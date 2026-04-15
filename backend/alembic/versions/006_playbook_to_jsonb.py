"""Change ai_config.conversion_playbook from TEXT to JSONB

Revision ID: 006
Revises: 005
Create Date: 2026-04-15

Note: Any existing free-form text in conversion_playbook is wiped on upgrade
(and on downgrade), because the old text shape does not map cleanly to the
new structured list shape.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "ai_config",
        "conversion_playbook",
        existing_type=sa.Text(),
        type_=JSONB(),
        existing_nullable=True,
        postgresql_using="NULL",
    )


def downgrade() -> None:
    op.alter_column(
        "ai_config",
        "conversion_playbook",
        existing_type=JSONB(),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="NULL",
    )
