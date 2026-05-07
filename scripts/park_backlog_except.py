"""
Park existing follow-up backlog by setting follow_up_attempts to the sentinel
value used by scripts (see FOLLOW_UP_PARKED_SENTINEL in
app/services/follow_up_engine.py).

This marks every conversation with follow_up_attempts=0 EXCEPT subscribers
whose ManyChat IDs you allow-list, so the dispatcher skips them
(`attempts >= len(rules)`). Use ONLY for deliberate bulk parking (e.g. smoke
tests on cold backlog).

⚠️  By default this script PRINTS ONLY (dry-run). Pass --execute to apply.

Undo: POST /api/admin/reset-follow-ups?campaign_id=... (JWT owner/admin).

Usage:
    python scripts/park_backlog_except.py [--execute] <manychat_id> [<manychat_id> ...]

Example (preview only — no DB writes):
    python scripts/park_backlog_except.py 560480135

Example (actually park everyone except Messa):
    python scripts/park_backlog_except.py --execute 560480135
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Must stay in sync with app.services.follow_up_engine.FOLLOW_UP_PARKED_SENTINEL
_PARK_SENTINEL = 99

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
load_dotenv(PROJECT_ROOT / "backend" / ".env")


def _asyncpg_url() -> str:
    raw = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_SYNC") or ""
    if not raw:
        print("ERROR: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)
    return raw.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres+asyncpg://", "postgres://"
    )


async def _run(allow_ids: list[str], *, execute: bool) -> None:
    import asyncpg

    conn = await asyncpg.connect(_asyncpg_url())
    try:
        before = await conn.fetchval(
            "SELECT COUNT(*) FROM conversations WHERE follow_up_attempts = 0"
        )
        kept = await conn.fetch(
            """
            SELECT s.manychat_subscriber_id, s.first_name, s.last_name
            FROM subscribers s
            WHERE s.manychat_subscriber_id = ANY($1::text[])
            """,
            allow_ids,
        )

        print(
            f"Would set follow_up_attempts={_PARK_SENTINEL} on conversations where "
            "follow_up_attempts=0,"
        )
        print(f"  excluding subscriber ManyChat IDs: {allow_ids!r}")
        print(f"Conversations currently at attempts=0: {before}")
        print(f"Allow-list ({len(kept)} found): "
              f"{[r['manychat_subscriber_id'] for r in kept]}")
        if not execute:
            print("\nDry-run — no UPDATE run. Pass --execute to apply.")
            return

        print("\nApplying UPDATE …")
        result = await conn.execute(
            """
            UPDATE conversations
            SET follow_up_attempts = $2
            WHERE follow_up_attempts = 0
              AND subscriber_id NOT IN (
                SELECT id FROM subscribers
                WHERE manychat_subscriber_id = ANY($1::text[])
              )
            """,
            allow_ids,
            _PARK_SENTINEL,
        )
        print(f"SQL result: {result}")

        after = await conn.fetchval(
            "SELECT COUNT(*) FROM conversations WHERE follow_up_attempts = 0"
        )
        print(f"Conversations remaining at attempts=0: {after}")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help=f"Actually run UPDATE follow_up_attempts={_PARK_SENTINEL} (default is dry-run only)",
    )
    parser.add_argument(
        "allow_ids",
        nargs="+",
        help="ManyChat subscriber IDs kept at follow_up_attempts=0",
    )
    args = parser.parse_args()
    allow_ids = [a.strip() for a in args.allow_ids if a.strip()]
    asyncio.run(_run(allow_ids, execute=args.execute))


if __name__ == "__main__":
    main()
