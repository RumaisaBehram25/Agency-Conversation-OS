"""
POST /api/settings/meta/integration-test
POST /api/settings/meta/sync-now

Optional: persist Meta settings, then call Meta Marketing API to verify
ad account access and return sample spend + campaign rows (Swagger-friendly).

sync-now kicks off a full ad-spend sync in the background for the current
org, populating daily_analytics / campaign_metrics / campaign_breakdowns.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_org_id
from app.database import async_session_factory, get_db
from app.integrations.meta.marketing_api import (
    fetch_ad_account_overview,
    fetch_campaign_metadata,
    fetch_daily_ad_spend,
)
from app.jobs.ad_spend_sync import sync_ad_spend
from app.models.campaign import AdCampaign
from app.models.organization import Organization
from app.models.user import OrgUser, User
from app.models.base import UserRole
from app.schemas.meta_integration_test import (
    MetaIntegrationTestRequest,
    MetaIntegrationTestResponse,
    MetaSyncNowRequest,
    MetaSyncNowResponse,
)
from app.security.encryption import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)

router = APIRouter()

_ENCRYPTED_META_FIELDS = {"meta_capi_token"}


async def _require_admin(
    db: AsyncSession,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    result = await db.execute(
        select(OrgUser)
        .where(OrgUser.user_id == user_id)
        .where(OrgUser.org_id == org_id)
    )
    membership = result.scalar_one_or_none()
    if membership is None or membership.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Requires owner or admin role.",
        )


@router.post("/meta/integration-test", response_model=MetaIntegrationTestResponse)
async def meta_integration_test(
    body: MetaIntegrationTestRequest,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> MetaIntegrationTestResponse:
    """
    Optionally save Meta fields on the organization, then fetch a live sample
    from Meta (ad account node, recent daily spend, campaign list).

    Requires owner or admin. Intended for validating credentials from Swagger.
    """
    membership_result = await db.execute(
        select(OrgUser)
        .where(OrgUser.user_id == current_user.id)
        .where(OrgUser.org_id == org_id)
    )
    membership = membership_result.scalar_one_or_none()

    if membership is None or membership.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Requires owner or admin role.",
        )

    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    persisted_names: list[str] = []
    if body.persist:
        payload = body.model_dump(
            exclude_unset=True,
            exclude_none=True,
            exclude={"persist", "spend_days", "campaigns_limit"},
        )
        for field_name, value in payload.items():
            if value is None:
                continue
            if field_name in _ENCRYPTED_META_FIELDS:
                value = encrypt_value(value)
            setattr(org, field_name, value)
            persisted_names.append(field_name)
        await db.flush()
        await db.refresh(org)

    # Effective values (saved org + optional same-request overrides when not persisting)
    ad_account_id = body.meta_ad_account_id or org.meta_ad_account_id
    pixel_id = body.meta_pixel_id or org.meta_pixel_id

    token_plain: str | None = None
    if body.meta_capi_token:
        token_plain = body.meta_capi_token
    elif org.meta_capi_token:
        try:
            token_plain = decrypt_value(org.meta_capi_token)
        except Exception:
            token_plain = None

    if not ad_account_id or not token_plain:
        return MetaIntegrationTestResponse(
            persisted=body.persist,
            persisted_field_names=persisted_names,
            effective_meta_ad_account_id=ad_account_id,
            effective_meta_pixel_id=pixel_id,
            access_token_configured=bool(token_plain),
            message="Set meta_ad_account_id and meta_capi_token (in the body and/or saved settings) to fetch Marketing API data.",
        )

    acct_json, acct_err = await fetch_ad_account_overview(ad_account_id, token_plain)
    if acct_err:
        return MetaIntegrationTestResponse(
            persisted=body.persist,
            persisted_field_names=persisted_names,
            effective_meta_ad_account_id=ad_account_id,
            effective_meta_pixel_id=pixel_id,
            access_token_configured=True,
            ad_account_error=acct_err,
            message="Could not read the ad account from Meta. Check the id and token permissions (ads_read on this account).",
        )

    date_to = date.today() - timedelta(days=1)
    date_from = date_to - timedelta(days=body.spend_days - 1)
    spend_rows = await fetch_daily_ad_spend(
        ad_account_id=ad_account_id,
        access_token=token_plain,
        date_from=date_from,
        date_to=date_to,
    )
    campaigns = await fetch_campaign_metadata(ad_account_id, token_plain)
    campaigns = campaigns[: body.campaigns_limit]

    ok = bool(acct_json)
    msg_parts = [
        "Ad account readable from Meta.",
        f"Spend rows in range: {len(spend_rows)}.",
        f"Campaigns returned: {len(campaigns)}.",
    ]
    if not spend_rows:
        msg_parts.append(
            "No daily spend in this window (new account, paused spend, or delay) — token may still be valid."
        )

    return MetaIntegrationTestResponse(
        persisted=body.persist,
        persisted_field_names=persisted_names,
        effective_meta_ad_account_id=ad_account_id,
        effective_meta_pixel_id=pixel_id,
        access_token_configured=True,
        ad_account=acct_json,
        daily_spend=spend_rows,
        campaigns=campaigns,
        ok=ok,
        message=" ".join(msg_parts),
    )


async def _auto_import_meta_campaigns(
    session: AsyncSession,
    org_id: uuid.UUID,
    ad_account_id: str,
    access_token: str,
) -> int:
    """
    Ensure every Meta campaign on the ad account has a matching ad_campaigns row.

    Missing campaigns are inserted with is_attora_managed=True + is_active=True
    (model defaults) so the granular sync picks them up. Existing rows are left
    untouched — this never flips a manually-unmanaged campaign back to managed.

    Returns the count of newly inserted rows.
    """
    campaigns = await fetch_campaign_metadata(ad_account_id, access_token)
    if not campaigns:
        return 0

    existing_result = await session.execute(
        select(AdCampaign.meta_campaign_id).where(
            AdCampaign.org_id == org_id,
            AdCampaign.meta_campaign_id.isnot(None),
        )
    )
    existing_ids = {row for row, in existing_result.all() if row}

    inserted = 0
    for camp in campaigns:
        meta_id = camp.get("campaign_id")
        if not meta_id or meta_id in existing_ids:
            continue
        session.add(
            AdCampaign(
                id=uuid.uuid4(),
                org_id=org_id,
                name=camp.get("name") or f"Meta campaign {meta_id}",
                meta_campaign_id=meta_id,
            )
        )
        inserted += 1

    if inserted:
        await session.flush()
        logger.info(
            "Auto-imported %d Meta campaign(s) as Attora-managed for org %s",
            inserted,
            org_id,
        )
    return inserted


async def _run_sync_in_background(
    org_id: uuid.UUID,
    ad_account_id: str,
    encrypted_token: str,
    days_back: int,
    granular: bool,
) -> None:
    """
    Auto-import campaigns, then run sync_ad_spend with a fresh session
    outside the request lifecycle.
    """
    async with async_session_factory() as session:
        try:
            if granular:
                try:
                    access_token = decrypt_value(encrypted_token)
                    imported = await _auto_import_meta_campaigns(
                        session, org_id, ad_account_id, access_token
                    )
                    if imported:
                        await session.commit()
                except Exception:
                    logger.exception(
                        "Auto-import of Meta campaigns failed for org %s; "
                        "continuing with sync on existing registrations",
                        org_id,
                    )
                    await session.rollback()

            result = await sync_ad_spend(
                session, days_back=days_back, granular=granular
            )
            logger.info("sync-now completed: %s", result)
        except Exception:
            logger.exception("sync-now failed")


@router.post(
    "/meta/sync-now",
    response_model=MetaSyncNowResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def meta_sync_now(
    body: MetaSyncNowRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> MetaSyncNowResponse:
    """
    Trigger a Meta Marketing API sync for the current org in the background.

    Populates daily_analytics, campaign_metrics, campaign_breakdowns, and
    ad_campaigns from the configured ad account. Requires owner or admin.
    """
    await _require_admin(db, current_user.id, org_id)

    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    if not org.meta_ad_account_id or not org.meta_capi_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Meta ad account is not configured for this organization. "
                "Set meta_ad_account_id and meta_capi_token in Settings first."
            ),
        )

    background_tasks.add_task(
        _run_sync_in_background,
        org.id,
        org.meta_ad_account_id,
        org.meta_capi_token,
        body.days_back,
        body.granular,
    )

    return MetaSyncNowResponse(
        started=True,
        days_back=body.days_back,
        granular=body.granular,
        message=(
            f"Meta sync started for the last {body.days_back} day(s). "
            "Analytics data will refresh in ~30–90 seconds."
        ),
    )
