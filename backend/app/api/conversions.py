"""
Attora — Conversion Ingestion API

POST /api/conversions/track — public endpoint called by the customer's landing
page / checkout / thank-you page. Authenticated via the X-Attora-Key header.

Records a ConversionEvent with the full UTM payload and, when the org has a
Meta pixel configured, fires the matching CAPI event (Lead / InitiateCheckout /
Purchase) as a fire-and-forget background task so the caller gets a fast 202.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_org_id_from_api_key
from app.database import async_session_factory, get_db
from app.integrations.meta.capi import (
    fire_initiate_checkout_event,
    fire_lead_event,
    fire_purchase_event,
)
from app.models.base import ConversionType
from app.models.campaign import AdCampaign
from app.models.conversion import ConversionEvent
from app.models.organization import Organization
from app.models.subscriber import Subscriber
from app.security.encryption import decrypt_value
from app.services.hyros_service import sync_single_subscriber_hyros_purchase

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────


class ConversionTrackRequest(BaseModel):
    """Landing-page / checkout / thank-you pixel payload."""

    conversion_type: ConversionType = Field(
        ..., description="Which funnel stage fired (lead, initiate_checkout, purchase)"
    )
    attora_sub: str = Field(
        ...,
        min_length=1,
        description="Subscriber id we appended to the UTM URL when messaging the lead",
    )
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    value: float | None = Field(None, ge=0)
    currency: str = "USD"


class ConversionTrackResponse(BaseModel):
    conversion_event_id: uuid.UUID
    capi_event_queued: bool
    attora_campaign_id: uuid.UUID | None


# ── Route ─────────────────────────────────────────────────────


@router.post(
    "/track",
    response_model=ConversionTrackResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def track_conversion(
    payload: ConversionTrackRequest,
    background_tasks: BackgroundTasks,
    org_id: uuid.UUID = Depends(get_org_id_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> ConversionTrackResponse:
    """
    Record a conversion event and queue a Meta CAPI dispatch.

    Flow:
      1. Resolve the subscriber by the attora_sub tag that was originally appended
         to the UTM URL. Subscriber must belong to the authenticated org.
      2. Resolve the AdCampaign: prefer an exact match on campaign_utms.utm_campaign,
         falling back to the subscriber's attora_campaign_id.
      3. Insert ConversionEvent with UTM + campaign attribution.
      4. Queue a background CAPI dispatch (Lead / InitiateCheckout / Purchase).
    """
    sub_result = await db.execute(
        select(Subscriber).where(
            Subscriber.org_id == org_id,
            Subscriber.manychat_subscriber_id == payload.attora_sub,
        )
    )
    subscriber = sub_result.scalar_one_or_none()
    if subscriber is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscriber '{payload.attora_sub}' not found for this org",
        )

    attora_campaign_id = await _resolve_campaign_id(
        db, org_id, payload.utm_campaign, subscriber.attora_campaign_id
    )

    meta_campaign_id: str | None = subscriber.campaign_id
    if attora_campaign_id is not None:
        camp_result = await db.execute(
            select(AdCampaign.meta_campaign_id).where(AdCampaign.id == attora_campaign_id)
        )
        meta_campaign_id = camp_result.scalar_one_or_none() or meta_campaign_id

    event = ConversionEvent(
        org_id=org_id,
        subscriber_id=subscriber.id,
        conversion_type=payload.conversion_type,
        value=payload.value,
        currency=payload.currency,
        ctwa_clid=subscriber.ctwa_clid,
        meta_ad_id=subscriber.ad_id,
        meta_campaign_id=meta_campaign_id,
        attora_campaign_id=attora_campaign_id,
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=payload.utm_campaign,
        utm_content=payload.utm_content,
        attora_sub=payload.attora_sub,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    # Look up pixel config for CAPI dispatch
    org_result = await db.execute(
        select(
            Organization.meta_pixel_id, Organization.meta_capi_token
        ).where(Organization.id == org_id)
    )
    org_row = org_result.one_or_none()

    capi_queued = False
    if org_row and org_row.meta_pixel_id and org_row.meta_capi_token:
        try:
            access_token = decrypt_value(org_row.meta_capi_token)
        except Exception:
            logger.error("Failed to decrypt meta_capi_token for org %s", org_id)
            access_token = None

        if access_token:
            background_tasks.add_task(
                _dispatch_capi_event,
                conversion_event_id=event.id,
                pixel_id=org_row.meta_pixel_id,
                access_token=access_token,
                conversion_type=payload.conversion_type,
                subscriber_manychat_id=subscriber.manychat_subscriber_id,
                channel=subscriber.channel.value if subscriber.channel else "messenger",
                ctwa_clid=subscriber.ctwa_clid,
                value=payload.value,
                currency=payload.currency,
            )
            capi_queued = True
    else:
        logger.info(
            "Skipping CAPI dispatch for org=%s: pixel/token not configured", org_id
        )

    background_tasks.add_task(
        _dispatch_hyros_sync,
        org_id=org_id,
        subscriber_id=subscriber.id,
    )

    return ConversionTrackResponse(
        conversion_event_id=event.id,
        capi_event_queued=capi_queued,
        attora_campaign_id=attora_campaign_id,
    )


# ── Helpers ───────────────────────────────────────────────────


async def _resolve_campaign_id(
    db: AsyncSession,
    org_id: uuid.UUID,
    utm_campaign: str | None,
    fallback_attora_campaign_id: uuid.UUID | None,
) -> uuid.UUID | None:
    """Prefer exact UTM match within the org; fall back to subscriber linkage."""
    if utm_campaign:
        from app.models.campaign import CampaignUTM

        result = await db.execute(
            select(CampaignUTM.campaign_id).where(
                CampaignUTM.org_id == org_id,
                CampaignUTM.utm_campaign == utm_campaign,
            )
        )
        matched = result.scalar_one_or_none()
        if matched is not None:
            return matched
    return fallback_attora_campaign_id


_CAPI_DISPATCH: dict[ConversionType, Any] = {
    ConversionType.LEAD: fire_lead_event,
    ConversionType.INITIATE_CHECKOUT: fire_initiate_checkout_event,
    ConversionType.PURCHASE: fire_purchase_event,
}


async def _dispatch_capi_event(
    *,
    conversion_event_id: uuid.UUID,
    pixel_id: str,
    access_token: str,
    conversion_type: ConversionType,
    subscriber_manychat_id: str,
    channel: str,
    ctwa_clid: str | None,
    value: float | None,
    currency: str,
) -> None:
    """Fire the CAPI event and flip capi_event_sent on success."""
    sender = _CAPI_DISPATCH.get(conversion_type)
    if sender is None:
        # upsell / unsupported types — skip CAPI
        logger.info(
            "No CAPI sender for conversion_type=%s (event %s); skipping",
            conversion_type,
            conversion_event_id,
        )
        return

    kwargs: dict[str, Any] = {
        "pixel_id": pixel_id,
        "access_token": access_token,
        "subscriber_id": subscriber_manychat_id,
        "channel": channel,
        "ctwa_clid": ctwa_clid,
    }
    if conversion_type is ConversionType.PURCHASE:
        # Purchase helper requires a value
        kwargs["value"] = value if value is not None else 0.0
        kwargs["currency"] = currency
    elif conversion_type is ConversionType.INITIATE_CHECKOUT:
        kwargs["value"] = value
        kwargs["currency"] = currency

    response = await sender(**kwargs)
    if response is None:
        return

    # Persist CAPI dispatch metadata
    events = response.get("events_received")
    capi_event_id = None
    if isinstance(response, dict):
        capi_event_id = response.get("fbtrace_id")

    async with async_session_factory() as session:
        await session.execute(
            update(ConversionEvent)
            .where(ConversionEvent.id == conversion_event_id)
            .values(
                capi_event_sent=True,
                capi_event_id=capi_event_id,
                capi_sent_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    logger.info(
        "CAPI dispatched: conversion_event=%s type=%s events_received=%s",
        conversion_event_id,
        conversion_type.value,
        events,
    )


async def _dispatch_hyros_sync(*, org_id: uuid.UUID, subscriber_id: uuid.UUID) -> None:
    """Best-effort Hyros sync for the converted subscriber."""
    async with async_session_factory() as session:
        await sync_single_subscriber_hyros_purchase(
            session,
            org_id=org_id,
            subscriber_id=subscriber_id,
        )
        await session.commit()
