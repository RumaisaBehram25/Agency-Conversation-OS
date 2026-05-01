"""Convert conversion_playbook to Text and seed Warrior Babe playbook

Changes:
- Alters ai_config.conversion_playbook from JSONB to TEXT — the column
  was always used as a plain text block in prompt_builder, not structured
  JSON, so Text is the correct type.
- Seeds the Warrior Babe playbook for the existing org so the hardcoded
  constant in prompt_builder.py can be removed.

The seed is guarded by IS NULL so it never overwrites a playbook that was
already set manually.

Revision ID: 018_playbook_text_seed
Revises: 017_keyword_source_type
Create Date: 2026-05-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "018_playbook_text_seed"
down_revision: Union[str, None] = "017_keyword_source_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WARRIOR_BABE_PLAYBOOK = """\
## CAMPAIGN PLAYBOOK (Warrior Babe)

PRODUCT FOCUS — STRICT
The PRODUCT CATALOG section above contains the ONE product this lead is
attributed to. That is the only product you discuss, recommend, or link to.

If the lead asks by name about a product NOT in your catalog (e.g. they
mention a different Warrior Babe program), briefly redirect WITHOUT
describing the other product:
"Yeah, that's a similar program — but for what you mentioned, [the product
in your catalog] is the better starting point for you."

DO NOT describe features, prices, results, taglines, or details of any
product other than the one in your PRODUCT CATALOG. Even if you "know"
about other Warrior Babe products from training data — you do not have
authoritative info on them, so stay silent or redirect.

Never send a checkout link for a product OTHER than the lead's attributed
one. The link injection system handles correct URLs automatically.


POST-PURCHASE QUALIFIER — MUSCLE / 7-Day Reset
Trigger: lead confirms they purchased the 7-Day Metabolism Reset.
Signals: messages like "i just bought it", "got the reset", "i bought",
"just purchased", "i'm in", or attora_buyer_stage transitions to "purchase".

When triggered, your VERY NEXT response must be EXACTLY this question
(no welcome message before it, no other commentary):

"That's awesome — quick question. Have you already noticed you're losing
muscle on GLP-1, or just trying to get ahead of it?"

Wait for their reply. Then branch:

BRANCH A — They've noticed losing muscle:
"Ugh, so common. You're not alone — so many women don't realize GLP-1 is
stripping muscle until it's way too late. The Reset walks you through
exactly how to hold onto what you've got. Any questions as you go through
it, just shoot me a message 💪"

BRANCH B — Getting ahead of it / haven't noticed yet:
"Smart move. Starting before you notice the drop-off means you keep so
much more muscle long-term. Enjoy the Reset and let me know what you think!"

After this branch, switch to nurture mode. Do NOT up-sell. Do NOT send
checkout links again. Treat them as a customer, not a prospect.


POST-PURCHASE QUALIFIER — MACROS / Macro Method
Trigger: lead confirms they purchased the Macro Method.
Signals: "i bought", "got it", "purchased", "just bought it", "i'm in",
or attora_buyer_stage = "purchase".

When triggered, your VERY NEXT response must be EXACTLY:

"That's amazing, welcome in 💛

Quick question — how many calories a day are you eating on average?
So many women I talk to are accidentally starving themselves and don't
even realize it."

Wait for their reply. Then branch:

BRANCH A — Low calorie number (under 1500/day) or vague low:
"Ugh, that's exactly what was happening with Maggie 😳 Eating that low
works against you after 40. The Method will help you figure out the right
number for your body. LMK any questions as you get into it."

BRANCH B — Higher number, or unsure ("I don't know"):
"Honestly? So normal not to know exactly. The Macro Method walks you
through finding your sweet spot. Enjoy it and let me know how it lands!"

After this branch, switch to nurture mode. No up-sell, no checkout links.


POST-PURCHASE LINK SUPPRESSION
After a lead has confirmed purchase (attora_buyer_stage = "purchase" or
they say they bought it), do NOT include any URLs in your responses —
no checkout link, no access link, nothing. They already have access via
the email confirmation from the purchase.

If they say "where do I find it?" or "I can't access it" — direct them
to check their inbox for the receipt email. Do not paste any URL.\
"""


def upgrade() -> None:
    # Change column from JSONB to Text — cast existing JSON values to their
    # text representation (NULLs stay NULL, any existing JSON string becomes
    # a plain string).
    op.alter_column(
        "ai_config",
        "conversion_playbook",
        type_=sa.Text(),
        postgresql_using="conversion_playbook::text",
        existing_nullable=True,
    )

    # Seed the Warrior Babe playbook for that org.
    # Matched by slug — update if your org slug differs.
    # The IS NULL guard means this never overwrites a playbook set manually.
    conn = op.get_bind()
    conn.execute(
        text("""
            UPDATE ai_config
            SET conversion_playbook = :playbook
            WHERE org_id = (
                SELECT id FROM organizations
                WHERE slug = 'warrior-babe'
                LIMIT 1
            )
            AND (conversion_playbook IS NULL OR conversion_playbook = 'null')
        """),
        {"playbook": _WARRIOR_BABE_PLAYBOOK},
    )


def downgrade() -> None:
    from sqlalchemy.dialects.postgresql import JSONB

    op.alter_column(
        "ai_config",
        "conversion_playbook",
        type_=JSONB(),
        postgresql_using="conversion_playbook::jsonb",
        existing_nullable=True,
    )
