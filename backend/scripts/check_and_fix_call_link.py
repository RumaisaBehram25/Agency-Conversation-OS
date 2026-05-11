"""
Check and optionally fix [CALL_LINK] placeholder in ai_config.system_prompt_override.

Reads the current system_prompt_override for the warrior-babe org and reports
whether it contains the literal token [CALL_LINK] or the real URL.

With --apply: replaces every occurrence of [CALL_LINK] with the real URL and
writes it back to the database.

Usage (from inside the api container):

    # Read-only — show current value
    docker compose exec api python -m scripts.check_and_fix_call_link --org warrior-babe

    # Apply the fix
    docker compose exec api python -m scripts.check_and_fix_call_link --org warrior-babe --apply
"""

import argparse
import asyncio
import sys
import uuid

from sqlalchemy import select

from app.database import async_session_factory
from app.models.ai_config import AIConfig
from app.models.organization import Organization

PLACEHOLDER = "[CALL_LINK]"
REAL_URL = "https://www.warriorbabe.com/schedule-apply"


async def _find_org(session, identifier: str) -> Organization | None:
    try:
        org_uuid = uuid.UUID(identifier)
        result = await session.execute(
            select(Organization).where(Organization.id == org_uuid)
        )
        org = result.scalar_one_or_none()
        if org is not None:
            return org
    except ValueError:
        pass

    result = await session.execute(
        select(Organization).where(Organization.slug == identifier)
    )
    return result.scalar_one_or_none()


async def _run(org_ident: str, apply: bool) -> int:
    async with async_session_factory() as session:
        org = await _find_org(session, org_ident)
        if org is None:
            print(f"ERROR: no org found for '{org_ident}'", file=sys.stderr)
            return 1

        ai_config = (
            await session.execute(
                select(AIConfig).where(AIConfig.org_id == org.id)
            )
        ).scalar_one_or_none()

        if ai_config is None:
            print(f"ERROR: no AIConfig row for org '{org.slug}' ({org.id})", file=sys.stderr)
            return 1

        current = ai_config.system_prompt_override

        if current is None:
            print(f"system_prompt_override is NULL for org '{org.slug}'")
            return 0

        has_placeholder = PLACEHOLDER in current
        has_real_url = REAL_URL in current

        print(f"\nOrg:               {org.slug} ({org.id})")
        print(f"Contains [CALL_LINK]:   {has_placeholder}")
        print(f"Contains real URL: {has_real_url}")
        print(f"\n--- system_prompt_override (first 800 chars) ---")
        print(current[:800])
        if len(current) > 800:
            print(f"\n... [{len(current) - 800} more characters]")
        print("--- end ---\n")

        if not apply:
            if has_placeholder:
                print("Run with --apply to replace [CALL_LINK] with the real URL.")
            else:
                print("No [CALL_LINK] placeholder found — nothing to fix.")
            return 0

        if not has_placeholder:
            print("No [CALL_LINK] placeholder found — nothing to change.")
            return 0

        updated = current.replace(PLACEHOLDER, REAL_URL)
        count = current.count(PLACEHOLDER)
        ai_config.system_prompt_override = updated
        await session.commit()

        print(f"Replaced {count} occurrence(s) of [CALL_LINK] with the real URL.")
        print(f"Committed to database.")
        return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Check/fix [CALL_LINK] placeholder in system_prompt_override."
    )
    p.add_argument("--org", required=True, help="Organization slug or UUID")
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write the fix to the database (default: read-only)",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run(args.org, args.apply))


if __name__ == "__main__":
    sys.exit(main())
