"""
Attora — FastAPI Dependencies

Shared dependencies for database sessions, authentication, and org scoping.
"""

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import OrgUser, User
from app.security.auth import decode_token

# OpenAPI + Swagger UI: registers HTTP Bearer so "Authorize" sends Authorization correctly.
_http_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_http_bearer),
    ],
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validate JWT from Authorization header and return the authenticated User.

    Raises 401 if:
    - No Authorization header
    - Token is invalid, expired, or not an access token
    - User not found or inactive
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise credentials_exception

    token = credentials.credentials

    try:
        payload = decode_token(token)
    except JWTError:
        raise credentials_exception

    # Verify this is an access token, not a refresh token
    if payload.get("type") != "access":
        raise credentials_exception

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_exception

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    return user


async def get_org_id(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """
    Resolve the org_id from the current user's org membership.

    For MVP, returns the first (and likely only) organization the user belongs to.
    In the future, this could accept an X-Org-Id header for multi-org users.

    Raises 403 if the user has no org membership.
    """
    result = await db.execute(
        select(OrgUser.org_id)
        .where(OrgUser.user_id == current_user.id)
        .limit(1)
    )
    org_id = result.scalar_one_or_none()

    if org_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a member of any organization",
        )

    return org_id


async def get_org_id_from_header(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    x_org_id: str | None = Header(None, description="Organization ID for multi-org users"),
) -> uuid.UUID:
    """
    Resolve org_id, preferring the X-Org-Id header if provided.

    Validates that the user actually belongs to the specified org.
    Falls back to get_org_id behavior if no header is provided.
    """
    if x_org_id:
        try:
            requested_org_id = uuid.UUID(x_org_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Org-Id header format",
            )

        # Verify membership
        result = await db.execute(
            select(OrgUser)
            .where(OrgUser.user_id == current_user.id)
            .where(OrgUser.org_id == requested_org_id)
        )
        membership = result.scalar_one_or_none()

        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a member of the specified organization",
            )

        return requested_org_id

    # Fall back to default org
    return await get_org_id(current_user=current_user, db=db)
