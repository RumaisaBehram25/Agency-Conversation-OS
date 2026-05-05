"""
Diagnose the ManyChat API key stored on an org.

Decrypts the manychat_api_key from Attora's DB (using ENCRYPTION_KEY
env var directly), prints a masked fingerprint, then hits ManyChat's
/page/getInfo with it. Tells you whether the key works and what the
account's API permissions actually look like.

Usage:
    python scripts/diag_manychat_key.py <org-slug>
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


def _decrypt(token: str) -> str:
    """Replicate app.security.encryption.decrypt_value without importing it."""
    from cryptography.fernet import Fernet

    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("ENCRYPTION_KEY env var not set")
    return Fernet(key.encode() if isinstance(key, str) else key).decrypt(
        token.encode() if isinstance(token, str) else token
    ).decode()


async def _run(slug: str) -> None:
    import asyncpg
    import httpx

    conn = await asyncpg.connect(_asyncpg_url())
    try:
        row = await conn.fetchrow(
            """
            SELECT id, name, manychat_api_key, manychat_page_id,
                   manychat_outbound_flow_ns
            FROM organizations
            WHERE slug = $1
            """,
            slug,
        )
        if row is None:
            print(f"ERROR: org slug={slug!r} not found")
            sys.exit(2)
        if not row["manychat_api_key"]:
            print("ERROR: org has no manychat_api_key set")
            sys.exit(3)

        try:
            api_key = _decrypt(row["manychat_api_key"])
        except Exception as e:
            print(f"ERROR: failed to decrypt manychat_api_key: {e}")
            sys.exit(4)
    finally:
        await conn.close()

    masked = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "<short>"
    print(f"Org           : {row['name']!r}")
    print(f"manychat_page : {row['manychat_page_id']}")
    print(f"outbound_ns   : {row['manychat_outbound_flow_ns']}")
    print(f"api key (mask): {masked}  (length {len(api_key)})")
    print()

    print("--> Calling https://api.manychat.com/fb/page/getInfo ...")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://api.manychat.com/fb/page/getInfo",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )

    print(f"  HTTP {r.status_code}")
    print(f"  body: {r.text[:600]}")
    print()

    if r.status_code == 200:
        print("OK -- API key valid AND Public API enabled on this account.")
        print("     The earlier 401 may have been transient. Re-run the cron.")
    elif r.status_code == 401:
        body = r.text.lower()
        if "integrations ability" in body or "only account" in body:
            print("FAIL -- Key structurally valid but account lacks API access.")
            print("        Even on Pro, ManyChat's 'Public API' toggle is OFF, OR")
            print("        the key was generated before the Pro upgrade.")
            print("        Fix: ManyChat -> Settings -> API -> enable + regenerate,")
            print("             then re-save the new key on the org.")
        else:
            print("FAIL -- 401, key rejected. Likely wrong/stale/expired.")
            print("        Fix: regenerate in ManyChat and update the org row.")
    else:
        print("UNEXPECTED -- inspect the body above.")


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(_run(sys.argv[1].strip()))


if __name__ == "__main__":
    main()
