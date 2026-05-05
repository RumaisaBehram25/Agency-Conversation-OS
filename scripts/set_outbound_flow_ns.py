"""
Set the ManyChat outbound flow namespace on an organization.

One-off config write. Run after creating the open "Attora Outbound"
flow in ManyChat, once per org.

Usage:
    python scripts/set_outbound_flow_ns.py <slug> <namespace>

Example:
    python scripts/set_outbound_flow_ns.py warrior-babe content20260504215152_657737

Uses asyncpg directly so no extra deps are needed beyond what the api
container already ships with.
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
    # asyncpg wants plain postgres[ql]:// — strip SQLAlchemy's driver suffix.
    return raw.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres+asyncpg://", "postgres://"
    )


async def _run(slug: str, namespace: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(_asyncpg_url())
    try:
        rows = await conn.fetch(
            """
            UPDATE organizations
            SET manychat_outbound_flow_ns = $1
            WHERE slug = $2
            RETURNING id, name, manychat_outbound_flow_ns
            """,
            namespace,
            slug,
        )
    finally:
        await conn.close()

    if not rows:
        print(f"ERROR: no organization with slug={slug!r}", file=sys.stderr)
        sys.exit(2)

    for row in rows:
        print(
            f"Updated org {row['name']!r} ({row['id']}) → "
            f"manychat_outbound_flow_ns = {row['manychat_outbound_flow_ns']}"
        )


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    asyncio.run(_run(sys.argv[1].strip(), sys.argv[2].strip()))


if __name__ == "__main__":
    main()
