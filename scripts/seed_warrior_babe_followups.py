"""
Attora — Warrior Babe Follow-up Sequences

Idempotent seed for the organic-comment campaigns **MUSCLE** and **MACROS**:
same four-touch copy and the same per-touch delays for both.

Timing (see `follow_up_engine.py`):
  - Touch 1: `after_minutes` since the lead's last inbound message (or conversation
    start if they never replied).
  - Touches 2–4: each `after_minutes` is counted from when the *previous* follow-up
    was sent — so 180 min means "no reply for 180 minutes after Touch 1", etc.

Touch 4 uses `[LINK]` so the engine substitutes the correct UTM + attora_sub /
attora_id URL for that subscriber and campaign (never hard-code example links).

Re-running is safe — upserts on (campaign_id, step_order).

Usage:
    python scripts/seed_warrior_babe_followups.py

Requires:
    - DATABASE_URL_SYNC or DATABASE_URL in project-root `.env` and/or `backend/.env`
    - Org `warrior-babe` and organic campaigns with keywords MUSCLE and MACROS
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
# Root `.env` (from .env.example) and optional `backend/.env` — backend wins if both set keys.
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env", override=True)


def _db_url() -> str:
    url = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL")
    if not url:
        root_env = PROJECT_ROOT / ".env"
        back_env = PROJECT_ROOT / "backend" / ".env"
        print(
            "ERROR: DATABASE_URL_SYNC or DATABASE_URL is not set.",
            file=sys.stderr,
        )
        print(
            f"  Add it to {root_env} and/or {back_env} (copy from .env.example).",
            file=sys.stderr,
        )
        print(
            "  Seed needs a sync driver URL, e.g. postgresql://user:pass@host:5432/dbname "
            "(use DATABASE_URL_SYNC, or DATABASE_URL without +asyncpg).",
            file=sys.stderr,
        )
        sys.exit(1)
    return url.replace("+asyncpg", "")


ORG_SLUG = "warrior-babe"

# Shared sequence for both MUSCLE and MACROS — (step_order, after_minutes, message, is_final)
WARRIOR_BABE_TOUCHES = [
    (
        1,
        1,
        (
            "Hey! Any questions about this?\n\n"
            "Honestly don't overthink it. it's way simpler than it sounds 😊"
        ),
        False,
    ),
    (
        2,
        1,
        (
            "One thing that really matters… this isn't a diet.\n\n"
            "The Method is about learning how to eat with your body after 40 — "
            "not against it.\n\n"
            "Most women I talk to are actually eating too little… and it's what's "
            "holding their fat loss back."
        ),
        False,
    ),
    (
        3,
        1,
        (
            "Still thinking it over? Totally fair.\n\n"
            "Just know that 21,000+ women over 35 have already used this exact "
            "method to feel better, look better, and get results that actually "
            "last.\n\n"
            "And right now, it's still 80% off.\n"
            "If you've got questions, just ask — I'm here."
        ),
        False,
    ),
    (
        4,
        1,
        (
            "Last note from me babe 🫶 The Method is yours for 80% off today. "
            "If you've been on the fence, here's your link: [LINK]"
        ),
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

        muscle_n = _upsert_touches(conn, org_id, muscle_id, WARRIOR_BABE_TOUCHES)
        macros_n = _upsert_touches(conn, org_id, macros_id, WARRIOR_BABE_TOUCHES)

    print(
        f"Seeded {muscle_n} MUSCLE touches and {macros_n} MACROS touches "
        f"for org {ORG_SLUG}."
    )
    print(
        "Reminder: set Organization.manychat_outbound_flow_ns for dispatch, and "
        "run follow-ups every 15 min via POST /api/cron/follow-ups or enable "
        "FOLLOW_UP_SCHEDULER_ENABLED=true (see scheduler / config)."
    )


if __name__ == "__main__":
    main()
