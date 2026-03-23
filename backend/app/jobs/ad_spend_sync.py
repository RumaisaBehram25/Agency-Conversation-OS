"""
Attora — Ad Spend Sync Job

Pulls daily ad spend from Meta Marketing API and upserts into
daily_analytics.ad_spend. Also computes cpa and roas when updating.

Run via POST /api/cron/ad-spend-sync (protected by X-Cron-Secret).
"""

import logging
import uuid
from datetime import date, timedelta

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.meta.marketing_api import fetch_daily_ad_spend
from app.models.analytics import DailyAnalytics
from app.models.organization import Organization
from app.security.encryption import decrypt_value

logger = logging.getLogger("attora.jobs.ad_spend_sync")


async def sync_ad_spend(
    db: AsyncSession,
    days_back: int = 7,
) -> dict:
    """
    Sync ad spend from Meta Marketing API for all configured orgs.

    Fetches the last `days_back` days of spend data and upserts into
    daily_analytics. Meta revises attribution data retroactively for
    up to 7 days, so re-fetching the last 7 days ensures accuracy.

    Returns summary of work done.
    """
    date_to = date.today() - timedelta(days=1)  # yesterday (Meta has ~3hr delay)
    date_from = date_to - timedelta(days=days_back - 1)

    # Load all orgs with a Meta ad account configured
    result = await db.execute(
        select(Organization).where(
            Organization.meta_ad_account_id.isnot(None),
            Organization.meta_ad_account_id != "",
            Organization.meta_capi_token.isnot(None),
            Organization.meta_capi_token != "",
        )
    )
    orgs = result.scalars().all()

    if not orgs:
        logger.info("Ad spend sync: no orgs with meta_ad_account_id configured")
        return {"orgs_processed": 0, "dates_updated": 0, "message": "No configured orgs"}

    total_dates_updated = 0
    total_spend = 0.0
    errors = []

    for org in orgs:
        try:
            # Decrypt the access token
            access_token = decrypt_value(org.meta_capi_token)
        except Exception as e:
            logger.error(f"Failed to decrypt meta_capi_token for org {org.id}: {e}")
            errors.append(f"org {org.id}: decrypt failed")
            continue

        # Fetch spend data from Meta
        spend_data = await fetch_daily_ad_spend(
            ad_account_id=org.meta_ad_account_id,
            access_token=access_token,
            date_from=date_from,
            date_to=date_to,
        )

        if not spend_data:
            logger.info(f"Ad spend sync: no spend data for org {org.id} ({org.name})")
            continue

        # Upsert into daily_analytics
        dates_updated = 0
        for entry in spend_data:
            spend_date = date.fromisoformat(entry["date"])
            spend_amount = entry["spend"]

            # Find existing daily_analytics row (channel=NULL for account-level totals)
            existing = await db.execute(
                select(DailyAnalytics).where(
                    and_(
                        DailyAnalytics.org_id == org.id,
                        DailyAnalytics.date == spend_date,
                        DailyAnalytics.channel.is_(None),
                    )
                )
            )
            row = existing.scalar_one_or_none()

            if row:
                # Update existing row
                row.ad_spend = spend_amount

                # Recompute CPA and ROAS
                if row.conversions and row.conversions > 0 and spend_amount > 0:
                    row.cpa = round(spend_amount / row.conversions, 2)
                else:
                    row.cpa = None

                if spend_amount > 0 and row.conversion_value:
                    row.roas = round(float(row.conversion_value) / spend_amount, 2)
                else:
                    row.roas = None
            else:
                # Create new row with just ad_spend (conversation data may not exist yet)
                new_row = DailyAnalytics(
                    id=uuid.uuid4(),
                    org_id=org.id,
                    date=spend_date,
                    channel=None,
                    ad_spend=spend_amount,
                    new_conversations=0,
                    active_conversations=0,
                    total_messages=0,
                    conversions=0,
                    conversion_value=0,
                    ai_tokens_used=0,
                    ai_cost=0,
                    fallback_count=0,
                )
                db.add(new_row)

            dates_updated += 1
            total_spend += spend_amount

        total_dates_updated += dates_updated
        logger.info(
            f"Ad spend sync: org {org.id} ({org.name}) — "
            f"{dates_updated} dates updated, total spend ${sum(e['spend'] for e in spend_data):.2f}"
        )

    await db.commit()

    summary = {
        "orgs_processed": len(orgs),
        "dates_updated": total_dates_updated,
        "total_spend": round(total_spend, 2),
        "date_range": f"{date_from} to {date_to}",
        "errors": errors if errors else None,
        "message": f"Synced {total_dates_updated} date(s) across {len(orgs)} org(s)",
    }
    logger.info(f"Ad spend sync complete: {summary}")
    return summary
