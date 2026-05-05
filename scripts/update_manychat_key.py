"""
Update an org's manychat_api_key with the encrypted form of a new key.

Usage:
    python scripts/update_manychat_key.py <org-slug> <new_api_key>

Example:
    python scripts/update_manychat_key.py warrior-babe 4545548:abc123def456...
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


def _encrypt(plaintext: str) -> str:
    from cryptography.fernet import Fernet

    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("ENCRYPTION_KEY env var not set")
    return Fernet(key.encode() if isinstance(key, str) else key).encrypt(
        plaintext.encode()
    ).decode()


async def _run(slug: str, new_key: str) -> None:
    import asyncpg

    encrypted = _encrypt(new_key)
    conn = await asyncpg.connect(_asyncpg_url())
    try:
        row = await conn.fetchrow(
            """
            UPDATE organizations
            SET manychat_api_key = $1, updated_at = now()
            WHERE slug = $2
            RETURNING id, name
            """,
            encrypted,
            slug,
        )
    finally:
        await conn.close()

    if row is None:
        print(f"ERROR: no org with slug={slug!r}")
        sys.exit(2)
    print(f"Updated manychat_api_key for {row['name']!r} ({row['id']}).")
    print("Re-run scripts/diag_manychat_key.py to verify the new key works.")


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    asyncio.run(_run(sys.argv[1].strip(), sys.argv[2].strip()))


if __name__ == "__main__":
    main()
