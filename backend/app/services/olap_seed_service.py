"""Helpers for seeding deterministic OLAP test data into PostgreSQL."""

from __future__ import annotations

import random
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import DailyAnalytics
from app.models.base import ChannelType
from app.models.campaign_metrics import CampaignBreakdown, CampaignMetric
from app.models.organization import Organization

DEFAULT_TEST_DATA_SEED = 20260417
CHANNELS = [ChannelType.MESSENGER, ChannelType.INSTAGRAM, ChannelType.WHATSAPP]
AGE_GENDER_KEYS = ["18-24_female", "25-34_female", "25-34_male", "35-44_male"]
PLATFORM_KEYS = ["messenger_inbox", "instagram_feed", "whatsapp_click_to_chat"]


@dataclass(slots=True)
class SeedOlapTestDataParams:
    date_from: date
    date_to: date
    org_id: uuid.UUID | None = None
    seed: int = DEFAULT_TEST_DATA_SEED
    campaign_count: int = 3
    adsets_per_campaign: int = 2
    ads_per_adset: int = 2
    replace_existing: bool = False


@dataclass(slots=True)
class SeedSummary:
    organizations: int = 0
    days: int = 0
    daily_created: int = 0
    daily_updated: int = 0
    campaign_created: int = 0
    campaign_updated: int = 0
    breakdown_created: int = 0
    breakdown_updated: int = 0


async def seed_olap_test_data(
    session: AsyncSession,
    params: SeedOlapTestDataParams,
) -> SeedSummary:
    if params.date_from > params.date_to:
        raise ValueError("date-from must be on or before date-to")
    if params.campaign_count < 1 or params.adsets_per_campaign < 1 or params.ads_per_adset < 1:
        raise ValueError("campaign/adset/ad counts must all be >= 1")

    summary = SeedSummary()
    organizations = await _resolve_organizations(session, params.org_id)
    if not organizations:
        raise ValueError("No organizations found. Create at least one org before seeding analytics data.")

    if params.replace_existing:
        await _delete_existing_rows(
            session,
            org_ids=[organization.id for organization in organizations],
            date_from=params.date_from,
            date_to=params.date_to,
        )

    summary.organizations = len(organizations)

    for organization in organizations:
        for row_date in _iter_dates(params.date_from, params.date_to):
            day_rng = _stable_rng(params.seed, organization.id, row_date.isoformat())
            total_ad_spend = round((120 + day_rng.randint(0, 110)) * (1 + day_rng.random() * 0.4), 2)
            daily_rows = _build_daily_rows(day_rng, row_date, total_ad_spend)
            combined_daily = next(row for row in daily_rows if row["channel"] is None)
            campaign_rows, breakdown_rows = _build_campaign_rows(
                seed=params.seed,
                org=organization,
                row_date=row_date,
                total_ad_spend=float(combined_daily["ad_spend"]),
                total_daily_conversions=int(combined_daily["conversions"]),
                campaign_count=params.campaign_count,
                adsets_per_campaign=params.adsets_per_campaign,
                ads_per_adset=params.ads_per_adset,
            )

            for values in daily_rows:
                created = await _upsert_daily_row(
                    session,
                    org_id=organization.id,
                    row_date=row_date,
                    values=values,
                )
                if created:
                    summary.daily_created += 1
                else:
                    summary.daily_updated += 1

            for values in campaign_rows:
                created = await _upsert_campaign_metric_row(
                    session,
                    org_id=organization.id,
                    values=values,
                )
                if created:
                    summary.campaign_created += 1
                else:
                    summary.campaign_updated += 1

            for values in breakdown_rows:
                created = await _upsert_campaign_breakdown_row(
                    session,
                    org_id=organization.id,
                    values=values,
                )
                if created:
                    summary.breakdown_created += 1
                else:
                    summary.breakdown_updated += 1

            summary.days += 1

    return summary


def summarize_seed_result(summary: SeedSummary) -> dict[str, int]:
    return {
        "organizations": summary.organizations,
        "org_days_processed": summary.days,
        "daily_created": summary.daily_created,
        "daily_updated": summary.daily_updated,
        "campaign_created": summary.campaign_created,
        "campaign_updated": summary.campaign_updated,
        "breakdown_created": summary.breakdown_created,
        "breakdown_updated": summary.breakdown_updated,
    }


def _iter_dates(date_from: date, date_to: date) -> Iterable[date]:
    current = date_from
    while current <= date_to:
        yield current
        current += timedelta(days=1)


def _normalize_weights(weights: list[float]) -> list[float]:
    total = sum(weights)
    if total <= 0:
        return [1 / len(weights)] * len(weights)
    return [weight / total for weight in weights]


def _split_integer(total: int, weights: list[float]) -> list[int]:
    normalized = _normalize_weights(weights)
    raw_values = [total * weight for weight in normalized]
    floored = [int(value) for value in raw_values]
    remainder = total - sum(floored)
    order = sorted(range(len(raw_values)), key=lambda idx: raw_values[idx] - floored[idx], reverse=True)
    for idx in order[:remainder]:
        floored[idx] += 1
    return floored


def _split_float(total: float, weights: list[float], digits: int = 2) -> list[float]:
    scale = 10**digits
    integer_values = _split_integer(int(round(total * scale)), weights)
    return [value / scale for value in integer_values]


def _stable_rng(seed: int, *parts: object) -> random.Random:
    token = ":".join(str(part) for part in parts)
    return random.Random(f"{seed}:{token}")


def _metric_payload(rng: random.Random, spend: float, leads: int) -> dict[str, float | int | None]:
    cpm = round(8.5 + rng.random() * 5.5, 4)
    impressions = max(100, int(round((spend * 1000) / cpm))) if spend > 0 else 0
    ctr = round(0.018 + rng.random() * 0.03, 4)
    clicks = max(leads, int(round(impressions * ctr))) if impressions > 0 else 0
    reach = max(clicks, int(round(impressions / (1.08 + rng.random() * 0.65)))) if impressions > 0 else 0
    frequency = round(impressions / reach, 4) if reach else None
    cpc = round(spend / clicks, 4) if clicks else None
    link_clicks = min(clicks, max(leads, int(round(clicks * (0.7 + rng.random() * 0.15))))) if clicks else 0
    landing_page_views = min(link_clicks, int(round(link_clicks * (0.72 + rng.random() * 0.16)))) if link_clicks else 0
    video_views = int(round(impressions * (0.14 + rng.random() * 0.1))) if impressions else 0
    post_engagement = int(round(clicks * (1.4 + rng.random() * 0.7))) if clicks else 0
    messaging_started = max(leads, int(round(leads * (1.35 + rng.random() * 0.5)))) if leads else 0
    messaging_first_reply = int(round(messaging_started * (0.6 + rng.random() * 0.18))) if messaging_started else 0
    return {
        "impressions": impressions,
        "clicks": clicks,
        "reach": reach,
        "frequency": frequency,
        "cpc": cpc,
        "cpm": cpm if spend > 0 else None,
        "ctr": ctr if impressions > 0 else None,
        "cost_per_lead": round(spend / leads, 2) if leads else None,
        "link_clicks": link_clicks,
        "landing_page_views": landing_page_views,
        "video_views": video_views,
        "post_engagement": post_engagement,
        "messaging_conversations_started": messaging_started,
        "messaging_first_reply": messaging_first_reply,
    }


def _build_daily_rows(
    rng: random.Random,
    row_date: date,
    total_ad_spend: float,
) -> list[dict[str, object]]:
    weekday_factor = 1 + ((row_date.weekday() + 1) / 14)
    total_new = int(round((26 + rng.randint(0, 18)) * weekday_factor))
    total_active = total_new + 6 + rng.randint(0, 10)
    total_messages = int(round(total_active * (3.2 + rng.random() * 1.8)))
    total_conversions = max(1, int(round(total_new * (0.09 + rng.random() * 0.06))))
    average_order_value = 85 + rng.randint(0, 75)
    total_conversion_value = round(total_conversions * average_order_value * (1 + rng.random() * 0.18), 2)
    total_ai_tokens = total_messages * (145 + rng.randint(0, 75))
    total_ai_cost = round((total_ai_tokens / 1000) * (0.004 + rng.random() * 0.002), 4)
    total_fallback = max(0, int(round(total_messages * (0.01 + rng.random() * 0.03))))
    base_response_time = 260 + rng.randint(0, 180)

    channel_weights = _normalize_weights(
        [
            0.48 + rng.random() * 0.06,
            0.31 + rng.random() * 0.05,
            0.21 + rng.random() * 0.04,
        ]
    )

    new_conversations = _split_integer(total_new, channel_weights)
    active_conversations = _split_integer(total_active, channel_weights)
    total_messages_by_channel = _split_integer(total_messages, channel_weights)
    conversions = _split_integer(total_conversions, channel_weights)
    conversion_values = _split_float(total_conversion_value, channel_weights, digits=2)
    ad_spend = _split_float(total_ad_spend, channel_weights, digits=2)
    ai_tokens_used = _split_integer(total_ai_tokens, channel_weights)
    ai_cost = _split_float(total_ai_cost, channel_weights, digits=4)
    fallback_count = _split_integer(total_fallback, channel_weights)

    rows: list[dict[str, object]] = []
    weighted_response_total = 0
    combined_active = 0

    for idx, channel in enumerate(CHANNELS):
        channel_response_time = base_response_time + int((idx - 1) * 22) + rng.randint(-12, 16)
        weighted_response_total += channel_response_time * active_conversations[idx]
        combined_active += active_conversations[idx]
        rows.append(
            {
                "channel": channel,
                "new_conversations": new_conversations[idx],
                "active_conversations": active_conversations[idx],
                "total_messages": total_messages_by_channel[idx],
                "avg_messages_per_conversation": round(total_messages_by_channel[idx] / active_conversations[idx], 2)
                if active_conversations[idx]
                else None,
                "avg_ai_response_time_ms": channel_response_time,
                "conversions": conversions[idx],
                "conversion_value": conversion_values[idx],
                "conversion_rate": round(conversions[idx] / new_conversations[idx], 4) if new_conversations[idx] else None,
                "ad_spend": ad_spend[idx],
                "cpa": round(ad_spend[idx] / conversions[idx], 2) if conversions[idx] else None,
                "roas": round(conversion_values[idx] / ad_spend[idx], 2) if ad_spend[idx] else None,
                "ai_tokens_used": ai_tokens_used[idx],
                "ai_cost": ai_cost[idx],
                "fallback_count": fallback_count[idx],
            }
        )

    rows.append(
        {
            "channel": None,
            "new_conversations": sum(new_conversations),
            "active_conversations": sum(active_conversations),
            "total_messages": sum(total_messages_by_channel),
            "avg_messages_per_conversation": round(sum(total_messages_by_channel) / sum(active_conversations), 2)
            if sum(active_conversations)
            else None,
            "avg_ai_response_time_ms": int(round(weighted_response_total / combined_active)) if combined_active else None,
            "conversions": sum(conversions),
            "conversion_value": round(sum(conversion_values), 2),
            "conversion_rate": round(sum(conversions) / sum(new_conversations), 4) if sum(new_conversations) else None,
            "ad_spend": round(sum(ad_spend), 2),
            "cpa": round(sum(ad_spend) / sum(conversions), 2) if sum(conversions) else None,
            "roas": round(sum(conversion_values) / sum(ad_spend), 2) if sum(ad_spend) else None,
            "ai_tokens_used": sum(ai_tokens_used),
            "ai_cost": round(sum(ai_cost), 4),
            "fallback_count": sum(fallback_count),
        }
    )
    return rows


def _build_campaign_rows(
    *,
    seed: int,
    org: Organization,
    row_date: date,
    total_ad_spend: float,
    total_daily_conversions: int,
    campaign_count: int,
    adsets_per_campaign: int,
    ads_per_adset: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    org_key = org.slug or str(org.id)
    lead_total = max(total_daily_conversions + campaign_count * 2, int(round(total_daily_conversions * 1.7)))
    campaign_weights = _normalize_weights(
        [campaign_count - idx + 0.35 for idx in range(campaign_count)]
    )
    campaign_spends = _split_float(total_ad_spend, campaign_weights, digits=2)
    campaign_leads = _split_integer(lead_total, campaign_weights)

    metric_rows: list[dict[str, object]] = []
    breakdown_rows: list[dict[str, object]] = []

    for campaign_idx in range(campaign_count):
        campaign_rng = _stable_rng(seed, org.id, row_date.isoformat(), "campaign", campaign_idx)
        campaign_id = f"seed_cmp_{org_key}_{campaign_idx + 1}"
        campaign_name = f"Seed Campaign {campaign_idx + 1}"
        campaign_spend = campaign_spends[campaign_idx]
        campaign_lead_count = campaign_leads[campaign_idx]
        campaign_status = "ACTIVE" if (row_date.toordinal() + campaign_idx) % 5 else "PAUSED"
        campaign_objective = "MESSAGES" if campaign_idx % 2 == 0 else "OUTCOME_LEADS"
        campaign_budget = round(campaign_spend * (1.18 + campaign_rng.random() * 0.16), 2)
        campaign_metrics = _metric_payload(campaign_rng, campaign_spend, campaign_lead_count)

        metric_rows.append(
            {
                "date": row_date,
                "level": "campaign",
                "meta_campaign_id": campaign_id,
                "meta_campaign_name": campaign_name,
                "meta_adset_id": None,
                "meta_adset_name": None,
                "meta_ad_id": None,
                "meta_ad_name": None,
                "status": campaign_status,
                "objective": campaign_objective,
                "daily_budget": campaign_budget,
                "spend": campaign_spend,
                "leads": campaign_lead_count,
                **campaign_metrics,
            }
        )

        adset_weights = _normalize_weights(
            [1.0 + ((adsets_per_campaign - adset_idx) * 0.15) + campaign_rng.random() * 0.25 for adset_idx in range(adsets_per_campaign)]
        )
        adset_spends = _split_float(campaign_spend, adset_weights, digits=2)
        adset_leads = _split_integer(campaign_lead_count, adset_weights)

        for adset_idx in range(adsets_per_campaign):
            adset_rng = _stable_rng(seed, org.id, row_date.isoformat(), "adset", campaign_idx, adset_idx)
            adset_id = f"seed_adset_{org_key}_{campaign_idx + 1}_{adset_idx + 1}"
            adset_name = f"Seed Adset {campaign_idx + 1}.{adset_idx + 1}"
            adset_spend = adset_spends[adset_idx]
            adset_lead_count = adset_leads[adset_idx]
            adset_metrics = _metric_payload(adset_rng, adset_spend, adset_lead_count)

            metric_rows.append(
                {
                    "date": row_date,
                    "level": "adset",
                    "meta_campaign_id": campaign_id,
                    "meta_campaign_name": campaign_name,
                    "meta_adset_id": adset_id,
                    "meta_adset_name": adset_name,
                    "meta_ad_id": None,
                    "meta_ad_name": None,
                    "status": campaign_status,
                    "objective": campaign_objective,
                    "daily_budget": round(adset_spend * (1.05 + adset_rng.random() * 0.2), 2),
                    "spend": adset_spend,
                    "leads": adset_lead_count,
                    **adset_metrics,
                }
            )

            ad_weights = _normalize_weights(
                [0.95 + ((ads_per_adset - ad_idx) * 0.12) + adset_rng.random() * 0.22 for ad_idx in range(ads_per_adset)]
            )
            ad_spends = _split_float(adset_spend, ad_weights, digits=2)
            ad_leads = _split_integer(adset_lead_count, ad_weights)

            for ad_idx in range(ads_per_adset):
                ad_rng = _stable_rng(seed, org.id, row_date.isoformat(), "ad", campaign_idx, adset_idx, ad_idx)
                ad_id = f"seed_ad_{org_key}_{campaign_idx + 1}_{adset_idx + 1}_{ad_idx + 1}"
                ad_name = f"Seed Ad {campaign_idx + 1}.{adset_idx + 1}.{ad_idx + 1}"
                ad_metrics = _metric_payload(ad_rng, ad_spends[ad_idx], ad_leads[ad_idx])

                metric_rows.append(
                    {
                        "date": row_date,
                        "level": "ad",
                        "meta_campaign_id": campaign_id,
                        "meta_campaign_name": campaign_name,
                        "meta_adset_id": adset_id,
                        "meta_adset_name": adset_name,
                        "meta_ad_id": ad_id,
                        "meta_ad_name": ad_name,
                        "status": campaign_status,
                        "objective": campaign_objective,
                        "daily_budget": round(ad_spends[ad_idx] * (1.02 + ad_rng.random() * 0.15), 2),
                        "spend": ad_spends[ad_idx],
                        "leads": ad_leads[ad_idx],
                        **ad_metrics,
                    }
                )

        age_gender_weights = [0.18, 0.34, 0.28, 0.2]
        platform_weights = [0.5, 0.3, 0.2]
        age_gender_spend = _split_float(campaign_spend, age_gender_weights, digits=2)
        age_gender_impressions = _split_integer(campaign_metrics["impressions"], age_gender_weights)
        age_gender_clicks = _split_integer(campaign_metrics["clicks"], age_gender_weights)
        age_gender_leads = _split_integer(campaign_lead_count, age_gender_weights)
        platform_spend = _split_float(campaign_spend, platform_weights, digits=2)
        platform_impressions = _split_integer(campaign_metrics["impressions"], platform_weights)
        platform_clicks = _split_integer(campaign_metrics["clicks"], platform_weights)
        platform_leads = _split_integer(campaign_lead_count, platform_weights)

        for idx, breakdown_key in enumerate(AGE_GENDER_KEYS):
            breakdown_rows.append(
                {
                    "date": row_date,
                    "meta_campaign_id": campaign_id,
                    "meta_adset_id": None,
                    "meta_ad_id": None,
                    "breakdown_type": "age_gender",
                    "breakdown_key": breakdown_key,
                    "spend": age_gender_spend[idx],
                    "impressions": age_gender_impressions[idx],
                    "clicks": age_gender_clicks[idx],
                    "leads": age_gender_leads[idx],
                }
            )

        for idx, breakdown_key in enumerate(PLATFORM_KEYS):
            breakdown_rows.append(
                {
                    "date": row_date,
                    "meta_campaign_id": campaign_id,
                    "meta_adset_id": None,
                    "meta_ad_id": None,
                    "breakdown_type": "platform",
                    "breakdown_key": breakdown_key,
                    "spend": platform_spend[idx],
                    "impressions": platform_impressions[idx],
                    "clicks": platform_clicks[idx],
                    "leads": platform_leads[idx],
                }
            )

    return metric_rows, breakdown_rows


async def _resolve_organizations(session: AsyncSession, org_id: uuid.UUID | None) -> list[Organization]:
    if org_id is not None:
        result = await session.execute(select(Organization).where(Organization.id == org_id))
        organization = result.scalar_one_or_none()
        if organization is None:
            raise ValueError(f"Organization not found: {org_id}")
        return [organization]

    result = await session.execute(select(Organization).order_by(Organization.slug.asc()))
    return list(result.scalars().all())


async def _delete_existing_rows(
    session: AsyncSession,
    *,
    org_ids: list[uuid.UUID],
    date_from: date,
    date_to: date,
) -> None:
    filters = [
        DailyAnalytics.org_id.in_(org_ids),
        DailyAnalytics.date >= date_from,
        DailyAnalytics.date <= date_to,
    ]
    await session.execute(delete(DailyAnalytics).where(and_(*filters)))
    await session.execute(
        delete(CampaignMetric).where(
            CampaignMetric.org_id.in_(org_ids),
            CampaignMetric.date >= date_from,
            CampaignMetric.date <= date_to,
        )
    )
    await session.execute(
        delete(CampaignBreakdown).where(
            CampaignBreakdown.org_id.in_(org_ids),
            CampaignBreakdown.date >= date_from,
            CampaignBreakdown.date <= date_to,
        )
    )


async def _upsert_daily_row(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    row_date: date,
    values: dict[str, object],
) -> bool:
    channel = values["channel"]
    query = select(DailyAnalytics).where(DailyAnalytics.org_id == org_id, DailyAnalytics.date == row_date)
    if channel is None:
        query = query.where(DailyAnalytics.channel.is_(None))
    else:
        query = query.where(DailyAnalytics.channel == channel)

    existing = (await session.execute(query)).scalar_one_or_none()
    if existing is None:
        session.add(DailyAnalytics(org_id=org_id, date=row_date, **values))
        return True

    for key, value in values.items():
        setattr(existing, key, value)
    return False


async def _upsert_campaign_metric_row(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    values: dict[str, object],
) -> bool:
    query = select(CampaignMetric).where(
        CampaignMetric.org_id == org_id,
        CampaignMetric.date == values["date"],
        CampaignMetric.level == values["level"],
        CampaignMetric.meta_campaign_id == values["meta_campaign_id"],
        CampaignMetric.meta_adset_id == values["meta_adset_id"],
        CampaignMetric.meta_ad_id == values["meta_ad_id"],
    )
    existing = (await session.execute(query)).scalar_one_or_none()
    if existing is None:
        session.add(CampaignMetric(org_id=org_id, **values))
        return True

    for key, value in values.items():
        setattr(existing, key, value)
    return False


async def _upsert_campaign_breakdown_row(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    values: dict[str, object],
) -> bool:
    query = select(CampaignBreakdown).where(
        CampaignBreakdown.org_id == org_id,
        CampaignBreakdown.date == values["date"],
        CampaignBreakdown.meta_campaign_id == values["meta_campaign_id"],
        CampaignBreakdown.meta_adset_id == values["meta_adset_id"],
        CampaignBreakdown.meta_ad_id == values["meta_ad_id"],
        CampaignBreakdown.breakdown_type == values["breakdown_type"],
        CampaignBreakdown.breakdown_key == values["breakdown_key"],
    )
    existing = (await session.execute(query)).scalar_one_or_none()
    if existing is None:
        session.add(CampaignBreakdown(org_id=org_id, **values))
        return True

    for key, value in values.items():
        setattr(existing, key, value)
    return False