"""
Attora — Organization API Routes

POST   /api/organizations                   — Create a new organization
GET    /api/organizations/{org_id}           — Get organization details
PUT    /api/organizations/{org_id}           — Update organization
POST   /api/organizations/{org_id}/rotate-key — Rotate the Attora API key
"""

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.organization import Organization
from app.models.user import OrgUser, User
from app.models.base import UserRole
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.security.encryption import decrypt_value, encrypt_value, mask_value
from app.api.deps import get_current_user

router = APIRouter()


def _generate_api_key() -> str:
    """Generate a secure random API key for webhook authentication."""
    return f"atk_{secrets.token_urlsafe(32)}"


def _org_to_response(org: Organization) -> OrganizationResponse:
    """
    Convert Organization model to response schema with masked sensitive fields.

    Decrypts sensitive fields first, then masks them for the response.
    """
    # Decrypt and mask sensitive fields
    decrypted_manychat_key = None
    if org.manychat_api_key:
        try:
            decrypted = decrypt_value(org.manychat_api_key)
            decrypted_manychat_key = mask_value(decrypted)
        except (ValueError, Exception):
            decrypted_manychat_key = "****[decrypt-error]"

    decrypted_capi_token = None
    if org.meta_capi_token:
        try:
            decrypted = decrypt_value(org.meta_capi_token)
            decrypted_capi_token = mask_value(decrypted)
        except (ValueError, Exception):
            decrypted_capi_token = "****[decrypt-error]"

    decrypted_api_key = None
    if org.attora_api_key:
        try:
            decrypted = decrypt_value(org.attora_api_key)
            decrypted_api_key = mask_value(decrypted)
        except (ValueError, Exception):
            decrypted_api_key = "****[decrypt-error]"

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        manychat_api_key=decrypted_manychat_key,
        manychat_page_id=org.manychat_page_id,
        manychat_account_id=org.manychat_account_id,
        meta_pixel_id=org.meta_pixel_id,
        meta_capi_token=decrypted_capi_token,
        meta_ad_account_id=org.meta_ad_account_id,
        meta_page_id=org.meta_page_id,
        meta_business_manager_id=org.meta_business_manager_id,
        attora_api_key=decrypted_api_key,
        plan=org.plan,
        monthly_conversation_limit=org.monthly_conversation_limit,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


async def _verify_org_membership(
    db: AsyncSession,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> OrgUser:
    """Verify the user is a member of the specified organization."""
    result = await db.execute(
        select(OrgUser)
        .where(OrgUser.user_id == user_id)
        .where(OrgUser.org_id == org_id)
    )
    membership = result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )
    return membership


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    request: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    """
    Create a new organization.

    Auto-generates an Attora API key and creates an 'owner' membership
    for the creating user. Encrypts sensitive fields before storage.
    """
    # Check slug uniqueness
    result = await db.execute(
        select(Organization).where(Organization.slug == request.slug)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An organization with this slug already exists",
        )

    # Generate and encrypt API key
    raw_api_key = _generate_api_key()
    encrypted_api_key = encrypt_value(raw_api_key)

    # Encrypt sensitive fields if provided
    encrypted_manychat_key = encrypt_value(request.manychat_api_key) if request.manychat_api_key else None
    encrypted_capi_token = encrypt_value(request.meta_capi_token) if request.meta_capi_token else None

    # Create organization
    org = Organization(
        name=request.name,
        slug=request.slug,
        manychat_api_key=encrypted_manychat_key,
        manychat_page_id=request.manychat_page_id,
        manychat_account_id=request.manychat_account_id,
        meta_pixel_id=request.meta_pixel_id,
        meta_capi_token=encrypted_capi_token,
        meta_ad_account_id=request.meta_ad_account_id,
        meta_page_id=request.meta_page_id,
        meta_business_manager_id=request.meta_business_manager_id,
        attora_api_key=encrypted_api_key,
        plan=request.plan,
        monthly_conversation_limit=request.monthly_conversation_limit,
    )
    db.add(org)
    await db.flush()

    # Create owner membership
    membership = OrgUser(
        user_id=current_user.id,
        org_id=org.id,
        role=UserRole.OWNER,
    )
    db.add(membership)
    await db.flush()

    return _org_to_response(org)


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    """
    Get organization details.

    Sensitive fields (API keys, tokens) are masked in the response.
    Requires org membership.
    """
    await _verify_org_membership(db, current_user.id, org_id)

    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()

    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    return _org_to_response(org)


@router.put("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: uuid.UUID,
    request: OrganizationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    """
    Update organization fields.

    Encrypts sensitive fields on write. Requires org membership with
    owner or admin role.
    """
    membership = await _verify_org_membership(db, current_user.id, org_id)

    # Only owners and admins can update
    if membership.role not in (UserRole.OWNER, UserRole.ADMIN):
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

    # Apply updates from request (only non-None fields)
    update_data = request.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if value is None:
            continue

        # Encrypt sensitive fields
        if field == "manychat_api_key":
            value = encrypt_value(value)
        elif field == "meta_capi_token":
            value = encrypt_value(value)

        setattr(org, field, value)

    await db.flush()
    await db.refresh(org)

    return _org_to_response(org)


@router.post("/{org_id}/rotate-key", response_model=dict)
async def rotate_api_key(
    org_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Generate a new Attora API key for webhook authentication.

    Returns the new key in plaintext (only time it's shown unmasked).
    The old key is immediately invalidated. Requires owner role.
    """
    membership = await _verify_org_membership(db, current_user.id, org_id)

    if membership.role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owners can rotate API keys",
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

    # Generate new key
    new_api_key = _generate_api_key()
    org.attora_api_key = encrypt_value(new_api_key)

    await db.flush()

    return {
        "message": "API key rotated successfully",
        "api_key": new_api_key,  # Show plaintext only once
        "warning": "Store this key securely. It will not be shown again.",
    }
