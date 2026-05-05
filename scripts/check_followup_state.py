"""
Check the post-send DB state for a single subscriber's follow-up.

Usage:
    python scripts/check_followup_state.py <manychat_id>

Example:
    python scripts/check_followup_state.py 560480135
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
    raw = os.getenv("DATABASE_URL") or ""
    return raw.replace("postgresql+asyncpg://", "postgresql://")


async def _run(manychat_id: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(_asyncpg_url())
    try:
        sub = await conn.fetchrow(
            """
            SELECT id, manychat_subscriber_id, first_name, last_name,
                   last_message_at, last_user_message_at,
                   buyer_stage, hyros_purchased
            FROM subscribers
            WHERE manychat_subscriber_id = $1
            """,
            manychat_id,
        )
        if sub is None:
            print(f"No subscriber with manychat_subscriber_id={manychat_id!r}")
            return

        print("=== SUBSCRIBER ===")
        for k, v in sub.items():
            print(f"  {k}: {v}")

        conv = await conn.fetchrow(
            """
            SELECT id, status, follow_up_attempts, last_follow_up_at,
                   last_activity_at
            FROM conversations
            WHERE subscriber_id = $1
            ORDER BY last_activity_at DESC NULLS LAST
            LIMIT 1
            """,
            sub["id"],
        )
        print("\n=== LATEST CONVERSATION ===")
        if conv is None:
            print("  (none)")
        else:
            for k, v in conv.items():
                print(f"  {k}: {v}")

            msgs = await conn.fetch(
                """
                SELECT created_at, sender, is_follow_up,
                       LEFT(content, 120) AS preview
                FROM messages
                WHERE conversation_id = $1
                ORDER BY created_at DESC
                LIMIT 5
                """,
                conv["id"],
            )
            print("\n=== LAST 5 MESSAGES ===")
            for m in msgs:
                tag = " [follow-up]" if m["is_follow_up"] else ""
                print(f"  {m['created_at']}  {m['sender']:<6}{tag}  {m['preview']!r}")
    finally:
        await conn.close()


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(_run(sys.argv[1].strip()))


if __name__ == "__main__":
    main()
