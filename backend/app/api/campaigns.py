"""
Attora — Ad Campaign & UTM API Routes

GET    /api/campaigns                     — List campaigns for org
POST   /api/campaigns                     — Create campaign
GET    /api/campaigns/{id}                — Get campaign details (includes UTM)
PUT    /api/campaigns/{id}                — Update campaign
DELETE /api/campaigns/{id}                — Delete campaign
POST   /api/campaigns/{id}/generate-utms  — Generate / regenerate UTM URLs
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
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

router = APIRouter()


async def _get_campaign_or_404(
    campaign_id: uuid.UUID,
    org_id: uuid.UUID,
    db: AsyncSession,
) -> AdCampaign:
    result = await db.execute(
        select(AdCampaign)
        .options(selectinload(AdCampaign.utm))
        .where(AdCampaign.id == campaign_id)
        .where(AdCampaign.org_id == org_id)
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


@router.get("", response_model=list[AdCampaignResponse])
async def list_campaigns(
    is_attora_managed: bool | None = None,
    is_active: bool | None = None,
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[AdCampaignResponse]:
    """List all ad campaigns for the organization."""
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

    result = await db.execute(query)
    campaigns = result.scalars().all()
    return [AdCampaignResponse.model_validate(c) for c in campaigns]


@router.post("", response_model=AdCampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    request: AdCampaignCreate,
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AdCampaignResponse:
    """Create a new ad campaign."""
    campaign = AdCampaign(
        org_id=org_id,
        name=request.name,
        description=request.description,
        meta_campaign_id=request.meta_campaign_id,
        meta_ad_set_id=request.meta_ad_set_id,
        is_attora_managed=request.is_attora_managed,
        product_id=request.product_id,
        is_active=request.is_active,
    )
    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)

    result = await db.execute(
        select(AdCampaign)
        .options(selectinload(AdCampaign.utm))
        .where(AdCampaign.id == campaign.id)
    )
    campaign = result.scalar_one()
    return AdCampaignResponse.model_validate(campaign)


@router.get("/{campaign_id}", response_model=AdCampaignResponse)
async def get_campaign(
    campaign_id: uuid.UUID,
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AdCampaignResponse:
    """Get campaign details including generated UTM URLs."""
    campaign = await _get_campaign_or_404(campaign_id, org_id, db)
    return AdCampaignResponse.model_validate(campaign)


@router.put("/{campaign_id}", response_model=AdCampaignResponse)
async def update_campaign(
    campaign_id: uuid.UUID,
    request: AdCampaignUpdate,
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AdCampaignResponse:
    """Update campaign fields."""
    campaign = await _get_campaign_or_404(campaign_id, org_id, db)

    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(campaign, field, value)

    await db.flush()
    await db.refresh(campaign)

    result = await db.execute(
        select(AdCampaign)
        .options(selectinload(AdCampaign.utm))
        .where(AdCampaign.id == campaign.id)
    )
    campaign = result.scalar_one()
    return AdCampaignResponse.model_validate(campaign)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: uuid.UUID,
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    """Delete a campaign and its associated UTMs."""
    campaign = await _get_campaign_or_404(campaign_id, org_id, db)
    await db.delete(campaign)
    await db.flush()


@router.post("/{campaign_id}/generate-utms", response_model=CampaignUTMResponse)
async def generate_utms(
    campaign_id: uuid.UUID,
    request: UTMGenerateRequest,
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CampaignUTMResponse:
    """
    Generate (or regenerate) UTM URLs for a campaign's conversion funnel.

    Provide base URLs for the product page, checkout page, and/or success page.
    Attora appends UTM parameters so you can track which visitors came from
    Attora-driven conversations.

    Copy the returned UTM URLs and apply them to your product pages.
    """
    campaign = await _get_campaign_or_404(campaign_id, org_id, db)

    utm_campaign_slug = request.utm_campaign or _slugify(campaign.name)

    product_utm, checkout_utm, success_utm = generate_utm_urls(
        utm_source=request.utm_source,
        utm_medium=request.utm_medium,
        utm_campaign=utm_campaign_slug,
        product_page_url=request.product_page_url,
        checkout_url=request.checkout_url,
        success_url=request.success_url,
    )

    # Upsert: update existing UTM record or create a new one
    if campaign.utm:
        utm = campaign.utm
        utm.utm_source = request.utm_source
        utm.utm_medium = request.utm_medium
        utm.utm_campaign = utm_campaign_slug
        if request.product_page_url is not None:
            utm.product_page_url = request.product_page_url
            utm.product_page_utm_url = product_utm
        if request.checkout_url is not None:
            utm.checkout_url = request.checkout_url
            utm.checkout_utm_url = checkout_utm
        if request.success_url is not None:
            utm.success_url = request.success_url
            utm.success_utm_url = success_utm
    else:
        utm = CampaignUTM(
            org_id=org_id,
            campaign_id=campaign_id,
            utm_source=request.utm_source,
            utm_medium=request.utm_medium,
            utm_campaign=utm_campaign_slug,
            product_page_url=request.product_page_url,
            checkout_url=request.checkout_url,
            success_url=request.success_url,
            product_page_utm_url=product_utm,
            checkout_utm_url=checkout_utm,
            success_utm_url=success_utm,
        )
        db.add(utm)

    await db.flush()
    await db.refresh(utm)
    return CampaignUTMResponse.model_validate(utm)


@router.get("/{campaign_id}/utms", response_model=CampaignUTMResponse)
async def get_utms(
    campaign_id: uuid.UUID,
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CampaignUTMResponse:
    """Get the current UTM URLs for a campaign."""
    campaign = await _get_campaign_or_404(campaign_id, org_id, db)

    if campaign.utm is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No UTMs generated yet. Call POST /generate-utms first.",
        )

    return CampaignUTMResponse.model_validate(campaign.utm)
