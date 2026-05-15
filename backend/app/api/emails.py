"""
Email API — org-scoped Resend settings and manual send trigger.

All routes require a Bearer JWT. `org_id` comes from the token (see get_org_id),
not from the request body, so the sample curl must include Authorization.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_org_id
from app.database import get_db
from app.models.base import UserRole
from app.models.subscriber import Subscriber
from app.models.user import OrgUser, User
from app.schemas.emails import EmailSendRequest, EmailSendResponse, EmailSettingsUpsert
from app.services.email_service import send_email
from app.security.encryption import mask_value

router = APIRouter(prefix="/emails", tags=["emails"])


async def _require_org_admin(
    db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(OrgUser)
        .where(OrgUser.user_id == user_id)
        .where(OrgUser.org_id == org_id)
    )
    membership = result.scalar_one_or_none()
    if membership is None or membership.role not in (
        UserRole.OWNER,
        UserRole.ADMIN,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Requires owner or admin role.",
        )


@router.post("/send", response_model=EmailSendResponse)
async def trigger_email(
    payload: EmailSendRequest,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> EmailSendResponse:
    result = await db.execute(
        select(Subscriber.id).where(
            Subscriber.id == payload.subscriber_id,
            Subscriber.org_id == org_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscriber not found for this organization",
        )

    raw = await send_email(
        db=db,
        org_id=org_id,
        subscriber_id=payload.subscriber_id,
        to_email=str(payload.to_email),
        subject=payload.subject,
        html=payload.html,
        trigger_type=payload.trigger_type,
        product_id=payload.product_id,
    )
    return EmailSendResponse(**raw)


@router.get("/settings/{org_id}")
async def get_email_settings(
    org_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    token_org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if org_id != token_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization mismatch",
        )
    row = (
        await db.execute(
            text(
                "SELECT * FROM organization_email_settings "
                "WHERE organization_id = :organization_id"
            ),
            {"organization_id": org_id},
        )
    ).mappings().first()
    if row is None:
        return {}

    data = dict(row)
    rk = data.get("resend_api_key")
    data["resend_api_key_configured"] = bool(rk and str(rk).strip())
    if rk:
        data["resend_api_key"] = mask_value(str(rk))
    else:
        data["resend_api_key"] = None
    return data


@router.post("/settings/{org_id}")
async def upsert_email_settings(
    org_id: uuid.UUID,
    payload: EmailSettingsUpsert,
    current_user: User = Depends(get_current_user),
    token_org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if org_id != token_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization mismatch",
        )

    await _require_org_admin(db, current_user.id, org_id)

    await db.execute(
        text(
            """
            INSERT INTO organization_email_settings
              (organization_id, emails_enabled, max_emails_per_user_per_month,
               min_days_between_emails, no_response_followup_days,
               from_name, from_email, reply_to, resend_api_key)
            VALUES (:organization_id, :emails_enabled, :max_emails_per_user_per_month,
                    :min_days_between_emails, :no_response_followup_days,
                    :from_name, :from_email, :reply_to, :resend_api_key)
            ON CONFLICT (organization_id) DO UPDATE SET
              emails_enabled = EXCLUDED.emails_enabled,
              max_emails_per_user_per_month =
                EXCLUDED.max_emails_per_user_per_month,
              min_days_between_emails = EXCLUDED.min_days_between_emails,
              no_response_followup_days = EXCLUDED.no_response_followup_days,
              from_name = EXCLUDED.from_name,
              from_email = EXCLUDED.from_email,
              reply_to = EXCLUDED.reply_to,
              resend_api_key =
                COALESCE(EXCLUDED.resend_api_key,
                         organization_email_settings.resend_api_key),
              updated_at = now()
            """
        ),
        {
            "organization_id": org_id,
            "emails_enabled": payload.emails_enabled,
            "max_emails_per_user_per_month": payload.max_emails_per_user_per_month,
            "min_days_between_emails": payload.min_days_between_emails,
            "no_response_followup_days": payload.no_response_followup_days,
            "from_name": payload.from_name,
            "from_email": str(payload.from_email),
            "reply_to": str(payload.reply_to) if payload.reply_to else None,
            "resend_api_key": payload.resend_api_key,
        },
    )
    return {"status": "saved"}
