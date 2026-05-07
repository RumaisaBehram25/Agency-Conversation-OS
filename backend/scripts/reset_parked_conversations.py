"""
Reset follow-up counters parked by scripts/park_backlog_except.py (attempts = 99).

Idempotent — running multiple times only updates rows still at sentinel 99.

    UPDATE conversations
    SET follow_up_attempts = 0, last_follow_up_at = NULL
    WHERE follow_up_attempts = 99

Must match FOLLOW_UP_PARKED_SENTINEL in app/services/follow_up_engine.py.

Usage (from repo root):

    cd backend
    python scripts/reset_parked_conversations.py

Requires DATABASE_URL_SYNC or DATABASE_URL with sync driver (+psycopg2).

After reset, POST /api/cron/follow-ups?dry_run=true should show skipped_sequence_complete
only for subscribers who genuinely finished naturally (attempts >= len(rules)).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Matches app.services.follow_up_engine.FOLLOW_UP_PARKED_SENTINEL
_PARK_SENTINEL = 99

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_ROOT.parent
load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".env")


def _sync_url() -> str:
    url = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL") or ""
    if not url:
        print("ERROR: DATABASE_URL_SYNC or DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)
    return url.replace("+asyncpg", "")


def main() -> None:
    engine = create_engine(_sync_url())
    with engine.begin() as conn:
        before = conn.execute(
            text("SELECT COUNT(*) FROM conversations WHERE follow_up_attempts = :s"),
            {"s": _PARK_SENTINEL},
        ).scalar_one()
        print(f"Conversations with follow_up_attempts={_PARK_SENTINEL}: {before}")
        result = conn.execute(
            text(
                """
                UPDATE conversations
                SET follow_up_attempts = 0, last_follow_up_at = NULL
                WHERE follow_up_attempts = :s
                """
            ),
            {"s": _PARK_SENTINEL},
        )
        updated = getattr(result, "rowcount", -1)
        print(f"Rows updated (reset): {updated}")


if __name__ == "__main__":
    main()
