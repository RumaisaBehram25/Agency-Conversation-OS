"""
Attora — Ad Spend Sync Job

Pulls daily ad spend from Meta Marketing API and upserts into
daily_analytics.ad_spend. Also computes cpa and roas when updating.

Optionally pulls granular campaign/adset/ad metrics and demographic
breakdowns into campaign_metrics and campaign_breakdowns tables.

Run via POST /api/cron/ad-spend-sync (protected by X-Cron-Secret).
"""

import logging
import uuid
from datetime import date, timedelta

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.meta.marketing_api import (
    fetch_ad_creatives,
    fetch_ad_insights,
    fetch_adset_insights,
    fetch_breakdown_insights,
    fetch_campaign_insights,
    fetch_campaign_metadata,
    fetch_daily_ad_spend,
)
from app.jobs.olap_exports import export_campaign_facts_to_olap
from app.models.analytics import DailyAnalytics
from app.models.campaign import AdCampaign
from app.models.campaign_metrics import CampaignBreakdown, CampaignMetric
from app.models.organization import Organization
from app.models.subscriber import Subscriber
from app.security.encryption import decrypt_value

logger = logging.getLogger("attora.jobs.ad_spend_sync")


async def sync_ad_spend(
    db: AsyncSession,
    days_back: int = 7,
    granular: bool = True,
    org_id: uuid.UUID | None = None,
    source_type: str | None = None,
) -> dict:
    """
    Sync ad spend from Meta Marketing API.

    When `org_id` is provided, syncs only that organization (used by the
    user-triggered /meta/sync-now endpoint). When omitted, syncs every
    organization that has Meta credentials configured (used by the cron
    job that keeps all tenants fresh).

    Fetches the last `days_back` days of spend data and upserts into
    daily_analytics. Meta revises attribution data retroactively for
    up to 7 days, so re-fetching the last 7 days ensures accuracy.

    When `granular` is True, also pulls campaign/adset/ad level metrics
    and demographic breakdowns into campaign_metrics and campaign_breakdowns.

    Returns summary of work done.
    """
    date_to = date.today() - timedelta(days=1)  # yesterday (Meta has ~3hr delay)
    date_from = date_to - timedelta(days=days_back - 1)

    # Load orgs with Meta credentials configured. Scope to a single org when
    # the caller supplied one (user-triggered sync); otherwise all orgs (cron).
    org_query = select(Organization).where(
        Organization.meta_ad_account_id.isnot(None),
        Organization.meta_ad_account_id != "",
        Organization.meta_capi_token.isnot(None),
        Organization.meta_capi_token != "",
    )
    if org_id is not None:
        org_query = org_query.where(Organization.id == org_id)
    result = await db.execute(org_query)
    orgs = result.scalars().all()

    if not orgs:
        logger.info("Ad spend sync: no orgs with meta_ad_account_id configured")
        return {"orgs_processed": 0, "dates_updated": 0, "message": "No configured orgs"}

    total_dates_updated = 0
    total_spend = 0.0
    total_campaigns_synced = 0
    total_adsets_synced = 0
    total_ads_synced = 0
    total_breakdowns_synced = 0
    total_olap_objects_written = 0
    total_olap_rows_written = 0
    total_creatives_synced = 0
    total_subscribers_backfilled = 0
    errors = []

    for org in orgs:
        try:
            # Decrypt the access token
            access_token = decrypt_value(org.meta_capi_token)
        except Exception as e:
            logger.error(f"Failed to decrypt meta_capi_token for org {org.id}: {e}")
            errors.append(f"org {org.id}: decrypt failed")
            continue

        # ── Account-level spend (existing behavior) ───────────────
        spend_data = await fetch_daily_ad_spend(
            ad_account_id=org.meta_ad_account_id,
            access_token=access_token,
            date_from=date_from,
            date_to=date_to,
        )

        if not spend_data:
            logger.info(f"Ad spend sync: no spend data for org {org.id} ({org.name})")
        else:
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

        # ── Granular metrics (campaign / adset / ad / breakdowns) ─
        if not granular:
            continue

        # Restrict ingestion to Attora-managed campaigns. If the org hasn't
        # registered any, skip granular ingest entirely — we do not want
        # metrics for campaigns we aren't authorized to act on.
        attora_campaign_ids = await _load_attora_meta_campaign_ids(db, org.id, source_type=source_type)
        if not attora_campaign_ids:
            logger.info(
                "Granular sync: org %s has no Attora-managed campaigns registered; "
                "skipping campaign/adset/ad/breakdown ingest",
                org.id,
            )
            continue

        def _is_tracked(entry: dict) -> bool:
            # Meta insights entries carry the key "campaign_id" (set via
            # extra_id_fields in _flatten_insight_row); they do NOT have a
            # "meta_campaign_id" field. Reading the wrong key was silently
            # filtering out every campaign/adset/ad/breakdown insight,
            # leaving campaign_metrics empty even after a successful sync.
            return entry.get("campaign_id") in attora_campaign_ids

        # Campaign-level insights
        campaign_data = await fetch_campaign_insights(
            ad_account_id=org.meta_ad_account_id,
            access_token=access_token,
            date_from=date_from,
            date_to=date_to,
        )
        for entry in campaign_data:
            if not _is_tracked(entry):
                continue
            total_campaigns_synced += await _upsert_campaign_metric(
                db, org.id, entry, level="campaign",
            )

        # Adset-level insights
        adset_data = await fetch_adset_insights(
            ad_account_id=org.meta_ad_account_id,
            access_token=access_token,
            date_from=date_from,
            date_to=date_to,
        )
        for entry in adset_data:
            if not _is_tracked(entry):
                continue
            total_adsets_synced += await _upsert_campaign_metric(
                db, org.id, entry, level="adset",
            )

        # Ad-level insights
        ad_data = await fetch_ad_insights(
            ad_account_id=org.meta_ad_account_id,
            access_token=access_token,
            date_from=date_from,
            date_to=date_to,
        )
        for entry in ad_data:
            if not _is_tracked(entry):
                continue
            total_ads_synced += await _upsert_campaign_metric(
                db, org.id, entry, level="ad",
            )

        # Breakdown insights (age_gender + platform)
        for breakdown_type in ("age_gender", "platform"):
            breakdown_data = await fetch_breakdown_insights(
                ad_account_id=org.meta_ad_account_id,
                access_token=access_token,
                date_from=date_from,
                date_to=date_to,
                breakdown_type=breakdown_type,
            )
            for entry in breakdown_data:
                if not _is_tracked(entry):
                    continue
                total_breakdowns_synced += await _upsert_campaign_breakdown(
                    db, org.id, entry,
                )

        # Campaign metadata (status, objective, daily_budget)
        metadata = await fetch_campaign_metadata(
            ad_account_id=org.meta_ad_account_id,
            access_token=access_token,
        )
        await _apply_campaign_metadata(db, org.id, metadata)

        try:
            await db.flush()
            olap_summary = await export_campaign_facts_to_olap(
                db,
                org.id,
                date_from,
                date_to,
            )
            total_olap_objects_written += olap_summary.get("objects_written", 0)
            total_olap_rows_written += (
                olap_summary.get("campaign_metrics_rows", 0)
                + olap_summary.get("campaign_breakdowns_rows", 0)
            )
        except Exception as e:
            logger.warning("OLAP export failed for org %s: %s", org.id, e)
            errors.append(f"org {org.id}: olap export failed")
        # Ad creatives (ad_id -> post_id mapping) + subscriber backfill
        creatives = await fetch_ad_creatives(
            ad_account_id=org.meta_ad_account_id,
            access_token=access_token,
        )
        creatives_synced = await _apply_ad_creatives(db, org.id, creatives)
        total_creatives_synced += creatives_synced

        backfilled = await _backfill_subscriber_post_ids(db, org.id)
        total_subscribers_backfilled += backfilled

        logger.info(
            f"Granular sync: org {org.id} ({org.name}) — "
            f"{len(campaign_data)} campaigns, {len(adset_data)} adsets, "
            f"{len(ad_data)} ads, {creatives_synced} creatives, "
            f"{backfilled} subscribers backfilled, breakdowns synced"
        )

    await db.commit()

    summary = {
        "orgs_processed": len(orgs),
        "dates_updated": total_dates_updated,
        "total_spend": round(total_spend, 2),
        "date_range": f"{date_from} to {date_to}",
        "campaigns_synced": total_campaigns_synced,
        "adsets_synced": total_adsets_synced,
        "ads_synced": total_ads_synced,
        "breakdowns_synced": total_breakdowns_synced,
        "olap_rows_written": total_olap_rows_written,
        "olap_objects_written": total_olap_objects_written,
        "creatives_synced": total_creatives_synced,
        "subscribers_backfilled": total_subscribers_backfilled,
        "errors": errors if errors else None,
        "message": f"Synced {total_dates_updated} date(s) across {len(orgs)} org(s)",
    }
    logger.info(f"Ad spend sync complete: {summary}")
    return summary


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------


async def _load_attora_meta_campaign_ids(
    db: AsyncSession,
    org_id: uuid.UUID,
    source_type: str | None = None,
) -> set[str]:
    """Return the set of meta_campaign_ids this org has flagged as Attora-managed."""
    query = select(AdCampaign.meta_campaign_id).where(
        AdCampaign.org_id == org_id,
        AdCampaign.is_attora_managed.is_(True),
        AdCampaign.is_active.is_(True),
        AdCampaign.meta_campaign_id.isnot(None),
    )
    if source_type is not None:
        query = query.where(AdCampaign.source_type == source_type)
    result = await db.execute(query)
    return {row for row, in result.all() if row}


async def _upsert_campaign_metric(
    db: AsyncSession,
    org_id: uuid.UUID,
    entry: dict,
    level: str,
) -> int:
    """
    Upsert a single row into campaign_metrics.

    Returns 1 to indicate one row was processed (for counting).
    """
    row_date = date.fromisoformat(entry["date"])

    # Determine entity IDs based on level
    meta_campaign_id = entry.get("campaign_id") or None
    meta_adset_id = (entry.get("adset_id") or None) if level in ("adset", "ad") else None
    meta_ad_id = (entry.get("ad_id") or None) if level == "ad" else None

    # Look up existing row by unique constraint fields
    existing = await db.execute(
        select(CampaignMetric).where(
            and_(
                CampaignMetric.org_id == org_id,
                CampaignMetric.date == row_date,
                CampaignMetric.level == level,
                CampaignMetric.meta_campaign_id == meta_campaign_id,
                CampaignMetric.meta_adset_id == meta_adset_id,
                CampaignMetric.meta_ad_id == meta_ad_id,
            )
        )
    )
    row = existing.scalar_one_or_none()

    if row:
        # Update existing row
        row.meta_campaign_name = entry.get("campaign_name") or row.meta_campaign_name
        if level in ("adset", "ad"):
            row.meta_adset_name = entry.get("adset_name") or row.meta_adset_name
        if level == "ad":
            row.meta_ad_name = entry.get("ad_name") or row.meta_ad_name
        row.spend = entry["spend"]
        row.impressions = entry.get("impressions", 0)
        row.clicks = entry.get("clicks", 0)
        row.reach = entry.get("reach", 0)
        row.frequency = entry.get("frequency")
        row.cpc = entry.get("cpc")
        row.cpm = entry.get("cpm")
        row.ctr = entry.get("ctr")
        row.leads = entry.get("leads", 0)
        row.cost_per_lead = entry.get("cost_per_lead")
        row.link_clicks = entry.get("link_clicks", 0)
        row.landing_page_views = entry.get("landing_page_views", 0)
        row.video_views = entry.get("video_views", 0)
        row.post_engagement = entry.get("post_engagement", 0)
        row.messaging_conversations_started = entry.get("messaging_conversations_started", 0)
        row.messaging_first_reply = entry.get("messaging_first_reply", 0)
    else:
        # Insert new row
        new_row = CampaignMetric(
            id=uuid.uuid4(),
            org_id=org_id,
            date=row_date,
            level=level,
            meta_campaign_id=meta_campaign_id,
            meta_campaign_name=entry.get("campaign_name"),
            meta_adset_id=meta_adset_id,
            meta_adset_name=entry.get("adset_name") if level in ("adset", "ad") else None,
            meta_ad_id=meta_ad_id,
            meta_ad_name=entry.get("ad_name") if level == "ad" else None,
            spend=entry["spend"],
            impressions=entry.get("impressions", 0),
            clicks=entry.get("clicks", 0),
            reach=entry.get("reach", 0),
            frequency=entry.get("frequency"),
            cpc=entry.get("cpc"),
            cpm=entry.get("cpm"),
            ctr=entry.get("ctr"),
            leads=entry.get("leads", 0),
            cost_per_lead=entry.get("cost_per_lead"),
            link_clicks=entry.get("link_clicks", 0),
            landing_page_views=entry.get("landing_page_views", 0),
            video_views=entry.get("video_views", 0),
            post_engagement=entry.get("post_engagement", 0),
            messaging_conversations_started=entry.get("messaging_conversations_started", 0),
            messaging_first_reply=entry.get("messaging_first_reply", 0),
        )
        db.add(new_row)

    return 1


async def _upsert_campaign_breakdown(
    db: AsyncSession,
    org_id: uuid.UUID,
    entry: dict,
) -> int:
    """
    Upsert a single row into campaign_breakdowns.

    Returns 1 to indicate one row was processed (for counting).
    """
    row_date = date.fromisoformat(entry["date"])
    meta_campaign_id = entry.get("campaign_id") or None
    breakdown_type = entry["breakdown_type"]
    breakdown_key = entry["breakdown_key"]

    # Look up existing row by unique constraint fields
    existing = await db.execute(
        select(CampaignBreakdown).where(
            and_(
                CampaignBreakdown.org_id == org_id,
                CampaignBreakdown.date == row_date,
                CampaignBreakdown.meta_campaign_id == meta_campaign_id,
                CampaignBreakdown.meta_adset_id.is_(None),
                CampaignBreakdown.meta_ad_id.is_(None),
                CampaignBreakdown.breakdown_type == breakdown_type,
                CampaignBreakdown.breakdown_key == breakdown_key,
            )
        )
    )
    row = existing.scalar_one_or_none()

    if row:
        row.spend = entry.get("spend", 0)
        row.impressions = entry.get("impressions", 0)
        row.clicks = entry.get("clicks", 0)
        row.leads = entry.get("leads", 0)
    else:
        new_row = CampaignBreakdown(
            id=uuid.uuid4(),
            org_id=org_id,
            date=row_date,
            meta_campaign_id=meta_campaign_id,
            meta_adset_id=None,
            meta_ad_id=None,
            breakdown_type=breakdown_type,
            breakdown_key=breakdown_key,
            spend=entry.get("spend", 0),
            impressions=entry.get("impressions", 0),
            clicks=entry.get("clicks", 0),
            leads=entry.get("leads", 0),
        )
        db.add(new_row)

    return 1


async def _apply_ad_creatives(
    db: AsyncSession,
    org_id: uuid.UUID,
    creatives: list[dict],
) -> int:
    """
    Populate CampaignMetric.post_id on all level='ad' rows for each
    (org_id, meta_ad_id) in the fetched creatives.

    The same post_id repeats across every daily row for the same ad —
    accepted denormalization (post_id is ad-identity, not a daily metric).

    Returns the count of {ad_id, post_id} mappings successfully applied.
    """
    applied = 0
    for entry in creatives:
        ad_id = entry.get("ad_id")
        post_id = entry.get("post_id")
        if not ad_id or not post_id:
            continue

        stmt = (
            update(CampaignMetric)
            .where(
                CampaignMetric.org_id == org_id,
                CampaignMetric.level == "ad",
                CampaignMetric.meta_ad_id == ad_id,
            )
            .values(post_id=post_id)
            .execution_options(synchronize_session=False)
        )
        await db.execute(stmt)
        applied += 1

    return applied


async def _backfill_subscriber_post_ids(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> int:
    """
    Fill Subscriber.post_id from cached CampaignMetric.post_id where null.

    Scoped by org_id on both sides to respect multi-tenant boundaries.
    """
    stmt = (
        update(Subscriber)
        .where(
            Subscriber.org_id == org_id,
            Subscriber.post_id.is_(None),
            Subscriber.ad_id.isnot(None),
            CampaignMetric.org_id == org_id,
            CampaignMetric.level == "ad",
            CampaignMetric.post_id.isnot(None),
            CampaignMetric.meta_ad_id == Subscriber.ad_id,
        )
        .values(post_id=CampaignMetric.post_id)
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(stmt)
    return result.rowcount or 0


async def _apply_campaign_metadata(
    db: AsyncSession,
    org_id: uuid.UUID,
    metadata: list[dict],
) -> None:
    """
    Update status, objective, and daily_budget on campaign-level
    CampaignMetric rows from campaign metadata.
    """
    for meta in metadata:
        campaign_id = meta.get("campaign_id")
        if not campaign_id:
            continue

        # Find all campaign-level rows for this org + campaign
        result = await db.execute(
            select(CampaignMetric).where(
                and_(
                    CampaignMetric.org_id == org_id,
                    CampaignMetric.level == "campaign",
                    CampaignMetric.meta_campaign_id == campaign_id,
                )
            )
        )
        rows = result.scalars().all()

        for row in rows:
            row.status = meta.get("status") or row.status
            row.objective = meta.get("objective") or row.objective
            if meta.get("daily_budget") is not None:
                try:
                    row.daily_budget = float(meta["daily_budget"]) / 100  # Meta returns cents
                except (ValueError, TypeError):
                    pass
