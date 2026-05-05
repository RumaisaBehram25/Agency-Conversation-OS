"""
Update an org's manychat_page_id.

Usage:
    python scripts/update_manychat_page_id.py <org-slug> <new_page_id>

Example:
    python scripts/update_manychat_page_id.py warrior-babe 967183323615679
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
    return (os.getenv("DATABASE_URL") or "").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _run(slug: str, new_page_id: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(_asyncpg_url())
    try:
        row = await conn.fetchrow(
            """
            UPDATE organizations
            SET manychat_page_id = $1, updated_at = now()
            WHERE slug = $2
            RETURNING id, name, manychat_page_id
            """,
            new_page_id,
            slug,
        )
    finally:
        await conn.close()

    if row is None:
        print(f"ERROR: no org with slug={slug!r}")
        sys.exit(2)
    print(
        f"Updated {row['name']!r} ({row['id']}) -> "
        f"manychat_page_id = {row['manychat_page_id']}"
    )


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    asyncio.run(_run(sys.argv[1].strip(), sys.argv[2].strip()))


if __name__ == "__main__":
    main()
