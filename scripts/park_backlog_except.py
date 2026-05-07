"""
Park existing follow-up backlog by setting follow_up_attempts=99 on every
active conversation EXCEPT a whitelist of ManyChat subscriber IDs. Use to
exclude old cold leads from a smoke test.

Usage:
    python scripts/park_backlog_except.py <manychat_id> [<manychat_id> ...]

Example (only allow Messa.25 through):
    python scripts/park_backlog_except.py 560480135
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

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


async def _run(allow_ids: list[str]) -> None:
    import asyncpg

    conn = await asyncpg.connect(_asyncpg_url())
    try:
        # Show what we're about to do.
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

        print(f"Conversations currently at attempts=0: {before}")
        print(f"Allow-list ({len(kept)} found): "
              f"{[r['manychat_subscriber_id'] for r in kept]}")

        # Park everyone NOT in the allow-list.
        result = await conn.execute(
            """
            UPDATE conversations
            SET follow_up_attempts = 99
            WHERE follow_up_attempts = 0
              AND subscriber_id NOT IN (
                SELECT id FROM subscribers
                WHERE manychat_subscriber_id = ANY($1::text[])
              )
            """,
            allow_ids,
        )
        print(f"Result: {result}")

        after = await conn.fetchval(
            "SELECT COUNT(*) FROM conversations WHERE follow_up_attempts = 0"
        )
        print(f"Conversations remaining at attempts=0: {after}")
    finally:
        await conn.close()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    allow_ids = [a.strip() for a in sys.argv[1:] if a.strip()]
    asyncio.run(_run(allow_ids))


if __name__ == "__main__":
    main()
