"""
Attora — Attora-Managed Ad Campaign & UTM API

CRUD over the `ad_campaigns` registry plus UTM URL generation so customers
can apply Attora-specific tracking to their product / checkout / success pages.

Only campaigns listed here should be treated as Attora-managed: leads arriving
via other campaign_ids are not contacted (compliance guard lives in the webhook
ingestion path).

Routes:
  GET    /api/campaigns                          — list registered campaigns (+ UTMs)
  POST   /api/campaigns                          — register a campaign
  GET    /api/campaigns/{id}                     — get one
  PATCH  /api/campaigns/{id}                     — update
  DELETE /api/campaigns/{id}                     — unregister
  POST   /api/campaigns/{id}/generate-utms       — (re)generate UTM URLs
  GET    /api/campaigns/{id}/utm-for-subscriber  — UTMs with subscriber_id appended
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_org_id
from app.database import get_db
from app.models.campaign import AdCampaign, CampaignUTM
from app.models.user import User
from app.schemas.campaign import (
    AdCampaignCreate,
    AdCampaignResponse,
    AdCampaignUpdate,
    CampaignUTMResponse,
    UTMGenerateRequest,
    _slugify,
    generate_utm_urls,
)
from app.utils.dm_links import DmSubscriberView, build_dm_link

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────


async def _load_campaign(
    db: AsyncSession, org_id: uuid.UUID, campaign_id: uuid.UUID
) -> AdCampaign:
    result = await db.execute(
        select(AdCampaign)
        .options(selectinload(AdCampaign.utm))
        .where(AdCampaign.id == campaign_id, AdCampaign.org_id == org_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found"
        )
    return campaign


# ── List / Create ─────────────────────────────────────────────


@router.get("", response_model=list[AdCampaignResponse])
async def list_campaigns(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    is_attora_managed: bool | None = Query(
        None, description="Filter by Attora-managed flag"
    ),
    is_active: bool | None = Query(None, description="Filter by active flag"),
    source_type: str | None = Query(
        None,
        pattern="^(paid|organic)$",
        description="Filter by source type: 'paid' or 'organic'",
    ),
) -> list[AdCampaignResponse]:
    """List ad campaigns registered for the org, with their UTM set eager-loaded."""
    query = (
        select(AdCampaign)
        .options(selectinload(AdCampaign.utm))
        .where(AdCampaign.org_id == org_id)
        .order_by(AdCampaign.created_at.desc())
    )
    if is_attora_managed is not None:
        query = query.where(AdCampaign.is_attora_managed == is_attora_managed)
    if is_active is not None:
        query = query.where(AdCampaign.is_active == is_active)
    if source_type is not None:
        query = query.where(AdCampaign.source_type == source_type)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("", response_model=AdCampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: AdCampaignCreate,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> AdCampaignResponse:
    """Register a new ad campaign. By default it is Attora-managed."""
    if payload.meta_campaign_id:
        existing = await db.execute(
            select(AdCampaign.id).where(
                AdCampaign.org_id == org_id,
                AdCampaign.meta_campaign_id == payload.meta_campaign_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Campaign with meta_campaign_id={payload.meta_campaign_id} "
                    "is already registered"
                ),
            )

    if payload.keyword:
        existing_kw = await db.execute(
            select(AdCampaign.id).where(
                AdCampaign.org_id == org_id,
                AdCampaign.keyword == payload.keyword,
            )
        )
        if existing_kw.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Campaign with keyword={payload.keyword} is already registered",
            )

    campaign = AdCampaign(
        org_id=org_id,
        name=payload.name,
        description=payload.description,
        meta_campaign_id=payload.meta_campaign_id,
        meta_ad_set_id=payload.meta_ad_set_id,
        source_type=payload.source_type,
        keyword=payload.keyword,
        is_attora_managed=payload.is_attora_managed,
        product_id=payload.product_id,
        is_active=payload.is_active,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign, attribute_names=["utm"])
    return campaign


# ── Detail / Update / Delete ──────────────────────────────────


@router.get("/{campaign_id}", response_model=AdCampaignResponse)
async def get_campaign(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> AdCampaignResponse:
    return await _load_campaign(db, org_id, campaign_id)


@router.patch("/{campaign_id}", response_model=AdCampaignResponse)
async def update_campaign(
    campaign_id: uuid.UUID,
    payload: AdCampaignUpdate,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> AdCampaignResponse:
    campaign = await _load_campaign(db, org_id, campaign_id)

    updates = payload.model_dump(exclude_unset=True)

    # Pre-check keyword conflict so we surface a clean 409 instead of an
    # IntegrityError from the partial unique index.
    if "keyword" in updates and updates["keyword"]:
        clash = await db.execute(
            select(AdCampaign.id).where(
                AdCampaign.org_id == org_id,
                AdCampaign.keyword == updates["keyword"],
                AdCampaign.id != campaign_id,
            )
        )
        if clash.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Campaign with keyword={updates['keyword']} is already registered",
            )

    for key, value in updates.items():
        setattr(campaign, key, value)

    # Enforce: organic campaigns must have a keyword after update.
    if campaign.source_type == "organic" and not campaign.keyword:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organic campaigns require a keyword",
        )

    await db.commit()
    await db.refresh(campaign, attribute_names=["utm"])
    return campaign


@router.delete(
    "/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_campaign(
    campaign_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    campaign = await _load_campaign(db, org_id, campaign_id)
    await db.delete(campaign)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── UTM Generation ────────────────────────────────────────────


@router.post(
    "/{campaign_id}/generate-utms",
    response_model=CampaignUTMResponse,
)
async def generate_campaign_utms(
    campaign_id: uuid.UUID,
    payload: UTMGenerateRequest,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> CampaignUTMResponse:
    """
    Generate (or regenerate) the three funnel-stage UTM URLs for a campaign.

    Any stage URL omitted in the request is cleared from the stored UTM set.
    """
    campaign = await _load_campaign(db, org_id, campaign_id)

    utm_campaign_slug = payload.utm_campaign or _slugify(campaign.name)

    product_utm, checkout_utm, success_utm = generate_utm_urls(
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=utm_campaign_slug,
        product_page_url=payload.product_page_url,
        checkout_url=payload.checkout_url,
        success_url=payload.success_url,
    )

    if campaign.utm is None:
        campaign.utm = CampaignUTM(
            org_id=org_id,
            campaign_id=campaign.id,
            utm_source=payload.utm_source,
            utm_medium=payload.utm_medium,
            utm_campaign=utm_campaign_slug,
            product_page_url=payload.product_page_url,
            checkout_url=payload.checkout_url,
            success_url=payload.success_url,
            product_page_utm_url=product_utm,
            checkout_utm_url=checkout_utm,
            success_utm_url=success_utm,
        )
    else:
        campaign.utm.utm_source = payload.utm_source
        campaign.utm.utm_medium = payload.utm_medium
        campaign.utm.utm_campaign = utm_campaign_slug
        campaign.utm.product_page_url = payload.product_page_url
        campaign.utm.checkout_url = payload.checkout_url
        campaign.utm.success_url = payload.success_url
        campaign.utm.product_page_utm_url = product_utm
        campaign.utm.checkout_utm_url = checkout_utm
        campaign.utm.success_utm_url = success_utm

    await db.commit()
    await db.refresh(campaign.utm)
    return campaign.utm


# ── Per-Subscriber UTM Tagging ────────────────────────────────


@router.get(
    "/{campaign_id}/utm-for-subscriber",
    response_model=CampaignUTMResponse,
)
async def get_utm_for_subscriber(
    campaign_id: uuid.UUID,
    subscriber_id: str = Query(
        ..., min_length=1, description="Subscriber identifier (ManyChat ID) to tag onto every UTM URL"
    ),
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> CampaignUTMResponse:
    """
    Return the campaign's funnel URLs with DM attribution appended: identity
    (`attora_sub`, `attora_id` when known) plus UTM medium forced to ``dm``,
    `utm_source` / `utm_campaign` from the campaign UTM row (merged into any
    existing query string).

    If the subscriber isn't in this org yet, only identity fields available
    from the ManyChat id are included (typically `attora_sub` only).
    """
    campaign = await _load_campaign(db, org_id, campaign_id)
    if campaign.utm is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign has no UTM set. Call generate-utms first.",
        )

    # Look up the subscriber so we can also stamp their internal UUID.
    from app.models.subscriber import Subscriber

    sub_result = await db.execute(
        select(Subscriber.id).where(
            Subscriber.org_id == org_id,
            Subscriber.manychat_subscriber_id == subscriber_id,
        )
    )
    subscriber_uuid = sub_result.scalar_one_or_none()

    utm = campaign.utm
    sub_view = DmSubscriberView(
        manychat_subscriber_id=subscriber_id,
        id=subscriber_uuid,
    )

    def _tag(url: str | None) -> str | None:
        if not url:
            return None
        return build_dm_link(
            url,
            sub_view,
            utm.utm_campaign or "",
            utm.utm_source or "",
        )

    return CampaignUTMResponse(
        id=utm.id,
        campaign_id=utm.campaign_id,
        utm_source=utm.utm_source,
        utm_medium=utm.utm_medium,
        utm_campaign=utm.utm_campaign,
        product_page_url=utm.product_page_url,
        checkout_url=utm.checkout_url,
        success_url=utm.success_url,
        product_page_utm_url=_tag(utm.product_page_utm_url),
        checkout_utm_url=_tag(utm.checkout_utm_url),
        success_utm_url=_tag(utm.success_utm_url),
        created_at=utm.created_at,
        updated_at=utm.updated_at,
    )
