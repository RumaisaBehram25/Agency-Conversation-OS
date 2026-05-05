"""
Resolve the active Attora-managed campaign + UTM row for DM link stamping.

Shared by `load_conversation_context` (dm_utm hints) and the AI engine
(`_load_subscriber_tagged_urls_with_product`) so DM UTM fields stay consistent.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.campaign import AdCampaign

logger = logging.getLogger(__name__)


async def fetch_managed_campaign_with_utm(
    db: AsyncSession,
    org_id: uuid.UUID,
    attora_campaign_id: str | None,
) -> AdCampaign | None:
    """
    Pick the same campaign the AI uses for tagged URLs: subscriber's managed
    campaign when `attora_campaign_id` resolves to a UUID, else fallback to
    the most recent active managed campaign that has a UTM row.
    """
    campaign_uuid: uuid.UUID | None = None
    if attora_campaign_id:
        try:
            campaign_uuid = uuid.UUID(attora_campaign_id)
        except (ValueError, TypeError):
            campaign_uuid = None

    try:
        query = (
            select(AdCampaign)
            .where(
                AdCampaign.org_id == org_id,
                AdCampaign.is_active.is_(True),
                AdCampaign.is_attora_managed.is_(True),
            )
            .options(selectinload(AdCampaign.utm))
            .order_by(AdCampaign.created_at.desc())
        )
        if campaign_uuid is not None:
            query = query.where(AdCampaign.id == campaign_uuid)

        result = await db.execute(query.limit(1))
        campaign = result.scalar_one_or_none()

        if campaign is None or campaign.utm is None:
            fallback_result = await db.execute(
                select(AdCampaign)
                .where(
                    AdCampaign.org_id == org_id,
                    AdCampaign.is_active.is_(True),
                    AdCampaign.is_attora_managed.is_(True),
                )
                .options(selectinload(AdCampaign.utm))
                .order_by(AdCampaign.created_at.desc())
                .limit(10)
            )
            candidates = fallback_result.scalars().all()
            campaign = next((c for c in candidates if c.utm is not None), None)

        return campaign
    except Exception as e:
        logger.warning(
            "Failed to resolve managed campaign UTM for org=%s attora_campaign_id=%s: %s",
            org_id,
            attora_campaign_id,
            e,
        )
        return None


def dm_utm_strings_from_campaign(campaign: AdCampaign | None) -> tuple[str | None, str | None]:
    """Return (utm_campaign, utm_source) for ConversationContext / prompt stamping."""
    if campaign is None or campaign.utm is None:
        return None, None
    u = campaign.utm
    return u.utm_campaign or None, u.utm_source or None


async def resolve_dm_utm_hints(
    db: AsyncSession,
    org_id: uuid.UUID,
    attora_campaign_id: str | None,
) -> tuple[str | None, str | None]:
    """Load utm_campaign + utm_source strings for DM product URL stamping."""
    campaign = await fetch_managed_campaign_with_utm(db, org_id, attora_campaign_id)
    return dm_utm_strings_from_campaign(campaign)
