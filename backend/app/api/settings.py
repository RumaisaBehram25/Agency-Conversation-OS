"""
Attora — Settings API Routes

GET  /api/settings  — Get org settings (sensitive fields masked)
PUT  /api/settings  — Update org settings (encrypts sensitive fields)
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.organization import Organization
from app.models.user import OrgUser, User
from app.models.base import UserRole
from app.schemas.settings import SettingsResponse, SettingsUpdate
from app.security.encryption import decrypt_value, encrypt_value, mask_value
from app.api.deps import get_current_user, get_org_id

router = APIRouter()

# Fields that must be encrypted before storage
_ENCRYPTED_FIELDS = {"manychat_api_key", "meta_capi_token"}


def _org_to_settings_response(org: Organization) -> SettingsResponse:
    """Convert Organization model to settings response with masked sensitive fields."""
    manychat_api_key_masked = None
    if org.manychat_api_key:
        try:
            decrypted = decrypt_value(org.manychat_api_key)
            manychat_api_key_masked = mask_value(decrypted)
        except (ValueError, Exception):
            manychat_api_key_masked = "****[decrypt-error]"

    meta_capi_token_masked = None
    if org.meta_capi_token:
        try:
            decrypted = decrypt_value(org.meta_capi_token)
            meta_capi_token_masked = mask_value(decrypted)
        except (ValueError, Exception):
            meta_capi_token_masked = "****[decrypt-error]"

    return SettingsResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        manychat_api_key=manychat_api_key_masked,
        manychat_page_id=org.manychat_page_id,
        manychat_account_id=org.manychat_account_id,
        meta_pixel_id=org.meta_pixel_id,
        meta_capi_token=meta_capi_token_masked,
        meta_ad_account_id=org.meta_ad_account_id,
        meta_page_id=org.meta_page_id,
        meta_business_manager_id=org.meta_business_manager_id,
        plan=org.plan,
        monthly_conversation_limit=org.monthly_conversation_limit,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


@router.get("", response_model=SettingsResponse)
async def get_settings(
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    """Get organization settings with masked sensitive fields."""
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()

    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    return _org_to_settings_response(org)


@router.put("", response_model=SettingsResponse)
async def update_settings(
    request: SettingsUpdate,
    current_user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    """
    Update organization settings.

    Only owner/admin can update. Encrypts sensitive fields before storage.
    """
    # Verify role
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

    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()

    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    update_data = request.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if value is None:
            continue
        # Encrypt sensitive fields
        if field in _ENCRYPTED_FIELDS:
            value = encrypt_value(value)
        setattr(org, field, value)

    await db.flush()
    await db.refresh(org)

    return _org_to_settings_response(org)
