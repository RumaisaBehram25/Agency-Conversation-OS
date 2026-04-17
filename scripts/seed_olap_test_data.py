"""Seed deterministic daily analytics and campaign facts for OLAP testing."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")

from sqlalchemy import and_, delete, select

from app.database import async_session_factory
from app.services.olap_seed_service import (
    DEFAULT_TEST_DATA_SEED,
    SeedOlapTestDataParams,
    seed_olap_test_data,
    summarize_seed_result,
)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"Invalid ISO date: {value}") from error


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed daily analytics and campaign metrics for OLAP testing.")
    parser.add_argument("--date-from", required=True, type=_parse_date, help="Inclusive start date (YYYY-MM-DD)")
    parser.add_argument("--date-to", required=True, type=_parse_date, help="Inclusive end date (YYYY-MM-DD)")
    parser.add_argument("--org-id", type=uuid.UUID, help="Seed a single organization UUID. Defaults to all orgs.")
    parser.add_argument("--seed", type=int, default=DEFAULT_TEST_DATA_SEED, help="Deterministic random seed.")
    parser.add_argument("--campaign-count", type=int, default=3, help="Campaigns per org per day.")
    parser.add_argument("--adsets-per-campaign", type=int, default=2, help="Ad sets per campaign.")
    parser.add_argument("--ads-per-adset", type=int, default=2, help="Ads per ad set.")
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete existing daily/campaign data in the selected window before seeding.",
    )
    return parser


async def seed_data(args: argparse.Namespace) -> dict[str, int]:
    params = SeedOlapTestDataParams(
        date_from=args.date_from,
        date_to=args.date_to,
        org_id=args.org_id,
        seed=args.seed,
        campaign_count=args.campaign_count,
        adsets_per_campaign=args.adsets_per_campaign,
        ads_per_adset=args.ads_per_adset,
        replace_existing=args.replace_existing,
    )

    async with async_session_factory() as session:
        summary = await seed_olap_test_data(session, params)
        await session.commit()
    return summarize_seed_result(summary)


async def _async_main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        summary = await seed_data(args)
    except Exception as error:
        print(f"ERROR: {error}")
        return 1

    print("Seed complete")
    print(f"organizations={summary['organizations']}")
    print(f"org_days_processed={summary['org_days_processed']}")
    print(f"daily_created={summary['daily_created']} daily_updated={summary['daily_updated']}")
    print(f"campaign_created={summary['campaign_created']} campaign_updated={summary['campaign_updated']}")
    print(f"breakdown_created={summary['breakdown_created']} breakdown_updated={summary['breakdown_updated']}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()