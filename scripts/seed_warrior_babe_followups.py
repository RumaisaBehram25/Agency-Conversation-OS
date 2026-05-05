"""
Attora — Warrior Babe Follow-up Sequences

Idempotent seed for the two organic-comment campaigns from the brief:

  1. MUSCLE  → 7-Day Metabolism Reset ($7)     — 3 touches: 60min, 3hr, 12hr
  2. MACROS  → Macro Method ($27)              — 4 touches: 60min, 3hr, 12hr, 24hr (final)

Touch text contains a literal `[LINK]` token that the follow-up engine
substitutes per-subscriber at send time with the campaign's stamped
checkout URL (carrying utm_*, attora_sub, attora_id).

Re-running this script is safe — it upserts on (campaign_id, step_order).

Usage:
    python scripts/seed_warrior_babe_followups.py

Requires:
    - DATABASE_URL_SYNC env var (or .env file in backend/)
    - The 'warrior-babe' org and its MUSCLE / MACROS campaigns must
      already exist (created via the dashboard's Campaigns page).
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
load_dotenv(PROJECT_ROOT / "backend" / ".env")


def _db_url() -> str:
    url = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL_SYNC (or DATABASE_URL) not set.", file=sys.stderr)
        sys.exit(1)
    # Alembic / sync engine wants psycopg2 driver, not asyncpg.
    return url.replace("+asyncpg", "")


ORG_SLUG = "warrior-babe"

MUSCLE_TOUCHES = [
    (
        1,
        60,
        "Hey! Any questions about the Reset? Honestly don't overthink it...way "
        "simpler than it sounds ",
        False,
    ),
    (
        2,
        180,
        "One thing about the Reset...it's built for women on GLP-1 who want to "
        "drop the weight without dropping their muscle with it. Helps to avoid "
        "the 'skinny fat' look.\n\nSo important, and most plans miss it.",
        False,
    ),
    (
        3,
        720,
        "Hey…checking back in. If you're on the fence, know that this is 100% "
        "made for busy women who've tried it all. It's so easy and simple to "
        "follow. And no dieting required. What do you think?",
        True,
    ),
]

MACROS_TOUCHES = [
    (
        1,
        60,
        "Hey! Any questions about the Method so far? Honestly don't let the "
        "word \"macros\" intimidate you…it's way simpler than it sounds ",
        False,
    ),
    (
        2,
        180,
        "One thing that helps...the Method isn't a diet. It's how to eat with "
        "your body after 40 instead of against it. Most women I talk to are "
        "eating way less…and it stops all their fat loss.",
        False,
    ),
    (
        3,
        720,
        "Still thinking about it? Totally get it. Just know 21,000+ women over "
        "35 have already used this exact method to look and feel better than "
        "they have in years. It's also 80% off. Questions?",
        False,
    ),
    (
        4,
        1440,
        "Last note from me babe The Method is yours for 80% off today. If "
        "you've been on the fence, here's your link: [LINK]",
        True,
    ),
]


def _resolve_org_id(conn) -> uuid.UUID:
    row = conn.execute(
        text("SELECT id FROM organizations WHERE slug = :slug"),
        {"slug": ORG_SLUG},
    ).first()
    if row is None:
        print(
            f"ERROR: organization with slug={ORG_SLUG!r} not found. "
            "Create it via the dashboard first.",
            file=sys.stderr,
        )
        sys.exit(2)
    return row[0]


def _resolve_campaign_id(conn, org_id: uuid.UUID, keyword: str) -> uuid.UUID:
    row = conn.execute(
        text(
            "SELECT id FROM ad_campaigns "
            "WHERE org_id = :org_id AND keyword = :kw AND source_type = 'organic'"
        ),
        {"org_id": str(org_id), "kw": keyword},
    ).first()
    if row is None:
        print(
            f"ERROR: organic campaign with keyword={keyword!r} not found "
            f"for org {ORG_SLUG}. Register it on the Campaigns page first.",
            file=sys.stderr,
        )
        sys.exit(3)
    return row[0]


def _upsert_touches(
    conn,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    touches: list[tuple[int, int, str, bool]],
) -> int:
    """Idempotent upsert keyed on (campaign_id, step_order)."""
    rows_affected = 0
    for step_order, after_minutes, message, is_final in touches:
        existing = conn.execute(
            text(
                "SELECT id FROM campaign_follow_ups "
                "WHERE campaign_id = :cid AND step_order = :step"
            ),
            {"cid": str(campaign_id), "step": step_order},
        ).first()

        if existing:
            conn.execute(
                text(
                    "UPDATE campaign_follow_ups "
                    "SET after_minutes = :mins, message = :msg, "
                    "    is_final = :fin, is_active = TRUE, updated_at = now() "
                    "WHERE id = :id"
                ),
                {
                    "mins": after_minutes,
                    "msg": message,
                    "fin": is_final,
                    "id": str(existing[0]),
                },
            )
        else:
            conn.execute(
                text(
                    "INSERT INTO campaign_follow_ups "
                    "(id, org_id, campaign_id, step_order, after_minutes, "
                    " message, is_final, is_active, created_at, updated_at) "
                    "VALUES (:id, :org, :cid, :step, :mins, :msg, :fin, "
                    "        TRUE, now(), now())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org": str(org_id),
                    "cid": str(campaign_id),
                    "step": step_order,
                    "mins": after_minutes,
                    "msg": message,
                    "fin": is_final,
                },
            )
        rows_affected += 1
    return rows_affected


def main() -> None:
    engine = create_engine(_db_url())
    with engine.begin() as conn:
        org_id = _resolve_org_id(conn)
        muscle_id = _resolve_campaign_id(conn, org_id, "MUSCLE")
        macros_id = _resolve_campaign_id(conn, org_id, "MACROS")

        muscle_n = _upsert_touches(conn, org_id, muscle_id, MUSCLE_TOUCHES)
        macros_n = _upsert_touches(conn, org_id, macros_id, MACROS_TOUCHES)

    print(f"Seeded {muscle_n} MUSCLE touches and {macros_n} MACROS touches "
          f"for org {ORG_SLUG}.")
    print("Reminder: Organization.manychat_outbound_flow_ns must also be "
          "set on the warrior-babe org for the dispatcher to send anything.")


if __name__ == "__main__":
    main()
