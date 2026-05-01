"""Add conversation_script to ad_campaigns

Each campaign can have its own post-purchase qualifier script, separate
from the org-level conversion_playbook. This prevents the AI from seeing
both MUSCLE and MACROS scripts at once and picking the wrong one.

Revision ID: 019_campaign_conversation_script
Revises: 018_playbook_text_seed
Create Date: 2026-05-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "019_campaign_conversation_script"
down_revision: Union[str, None] = "018_playbook_text_seed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MUSCLE_SCRIPT = """\
## CAMPAIGN SCRIPT — 7-Day Metabolism Reset (MUSCLE)

POST-PURCHASE QUALIFIER
Trigger: the lead's current message confirms they purchased (any of: "i just bought it",
"i bought it", "just bought it", "i bought", "i purchased", "i just purchased",
"just purchased", "i got it", "i'm in", "im in").

When triggered, your response_text MUST be ONLY this exact text — no greeting, no \
"congrats", no other words before or after:
"Quick question...have you already noticed you're losing muscle, or just trying to get \
ahead of it?"

Wait for their reply. Then branch:

BRANCH A — They've noticed losing muscle (respond with exactly):
"Ugh, so common. You're not alone...so many women don't realize GLP-1 is stripping \
muscle until it's way too late. The Reset walks you through exactly how to hold onto \
what you've got. Any questions as you go through it, just shoot me a message 💪"

BRANCH B — Getting ahead of it / haven't noticed yet (respond with exactly):
"Smart move. Starting before you notice the drop-off means you keep so much more \
muscle long-term. Enjoy the Reset and let me know what you think!"

After either branch: switch to nurture mode. No upsell. No checkout links. No URLs.\
"""

_MACROS_SCRIPT = """\
## CAMPAIGN SCRIPT — Macro Method (MACROS)

POST-PURCHASE QUALIFIER
Trigger: the lead's current message confirms they purchased (any of: "i just bought it",
"i bought it", "just bought it", "i bought", "i purchased", "i just purchased",
"just purchased", "i got it", "i'm in", "im in").

When triggered, your response_text MUST be ONLY this exact text — no greeting, no \
extra commentary before or after:
"Quick question...how many calories a day are you eating on average? So many women \
I talk to are accidentally starving themselves."

Wait for their reply. Then branch:

BRANCH A — Low calorie number or vague low (respond with exactly):
"Yeah, that's exactly what was happening with Maggie. Eating that low works against \
you after 40 😳 The Method will help you figure out the right number for your body. \
LMK any questions as you get into it."

BRANCH B — Higher number or unsure (respond with exactly):
"Honestly? So normal not to know exactly. The Macro Method walks you through finding \
your sweet spot. Enjoy it and let me know how it lands!"

After either branch: switch to nurture mode. No upsell. No checkout links. No URLs.\
"""


def upgrade() -> None:
    op.add_column(
        "ad_campaigns",
        sa.Column("conversation_script", sa.Text(), nullable=True),
    )

    conn = op.get_bind()
    conn.execute(
        text("UPDATE ad_campaigns SET conversation_script = :s WHERE UPPER(keyword) = 'MUSCLE'"),
        {"s": _MUSCLE_SCRIPT},
    )
    conn.execute(
        text("UPDATE ad_campaigns SET conversation_script = :s WHERE UPPER(keyword) = 'MACROS'"),
        {"s": _MACROS_SCRIPT},
    )


def downgrade() -> None:
    op.drop_column("ad_campaigns", "conversation_script")
