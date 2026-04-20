"""
Set ai_config.conversion_playbook for a specific organization from a JSON list.

Admin-only. Orgs do not run this themselves.

Usage (from inside the api container):

    # From a file that is mounted inside the container
    docker compose exec -T api python -m scripts.set_conversion_playbook \\
        --org <slug-or-uuid> --file /app/path/to/playbook.json

    # From stdin (typical — when the JSON lives outside the container)
    docker compose exec -T api python -m scripts.set_conversion_playbook \\
        --org <slug-or-uuid> --file - < warrior_babe_carousels.json

    # Dry run (no writes, just validates input and shows what would change)
    docker compose exec -T api python -m scripts.set_conversion_playbook \\
        --org <slug-or-uuid> --file - --dry-run < warrior_babe_carousels.json
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app.database import async_session_factory
from app.models.ai_config import AIConfig
from app.models.organization import Organization
from app.redis import close_redis, init_redis
from app.services.config_loader import invalidate_org_config


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


def _load_playbook(path: str) -> list:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text()
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError(
            f"conversion_playbook must be a JSON list, got {type(data).__name__}"
        )
    return data


async def _run(org_ident: str, playbook: list, dry_run: bool) -> int:
    redis_client = await init_redis()
    try:
        async with async_session_factory() as session:
            org = await _find_org(session, org_ident)
            if org is None:
                print(f"ERROR: no org found for '{org_ident}'", file=sys.stderr)
                return 1

            ai_config_row = (
                await session.execute(
                    select(AIConfig).where(AIConfig.org_id == org.id)
                )
            ).scalar_one_or_none()

            before_len = (
                len(ai_config_row.conversion_playbook)
                if ai_config_row is not None
                and ai_config_row.conversion_playbook is not None
                else None
            )
            new_len = len(playbook)

            if dry_run:
                print(f"[dry-run] org:                 {org.slug} ({org.id})")
                print(f"[dry-run] AIConfig row exists: {ai_config_row is not None}")
                print(f"[dry-run] current items:       {before_len}")
                print(f"[dry-run] would set items:     {new_len}")
                return 0

            if ai_config_row is None:
                ai_config_row = AIConfig(org_id=org.id, conversion_playbook=playbook)
                session.add(ai_config_row)
                action = "created AIConfig row"
            else:
                ai_config_row.conversion_playbook = playbook
                action = "updated AIConfig row"

            await session.commit()
            await invalidate_org_config(org.id, redis_client=redis_client)

            print(f"✓ {action} for org {org.slug} ({org.id})")
            print(f"  previous items: {before_len}")
            print(f"  new items:      {new_len}")
            return 0
    finally:
        await close_redis()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Set ai_config.conversion_playbook for one organization."
    )
    p.add_argument("--org", required=True, help="Organization slug or UUID")
    p.add_argument(
        "--file",
        required=True,
        help="Path to a JSON file containing the playbook list, or '-' for stdin",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate input and look up the org, but do not write to the database",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        playbook = _load_playbook(args.file)
    except (json.JSONDecodeError, ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return asyncio.run(_run(args.org, playbook, args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
