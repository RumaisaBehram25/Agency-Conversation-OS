"""
Attora — FastAPI Dependencies

Shared dependencies for database sessions, authentication, and org scoping.
"""

import hashlib
import uuid

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.organization import Organization
from app.models.user import OrgUser, User
from app.redis import get_redis_pool
from app.security.auth import decode_token
from app.security.encryption import decrypt_value

bearer_scheme = HTTPBearer(
    bearerFormat="JWT",
    description="Paste the access_token returned by /api/auth/login",
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
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


async def get_org_id_from_api_key(
    x_attora_key: str = Header(..., description="Attora API key"),
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """
    Authenticate a request via the X-Attora-Key header and return the org_id.

    Used by webhook / conversion-ingest endpoints that are called by the customer's
    landing-page or server, not by a logged-in user. Key -> org_id mapping is cached
    in Redis to avoid decrypting every stored key on every request.
    """
    if not x_attora_key or len(x_attora_key) < 8:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )

    key_hash = hashlib.sha256(x_attora_key.encode()).hexdigest()[:16]
    cache_key = f"apikey:{key_hash}"

    try:
        redis = get_redis_pool()
        cached = await redis.get(cache_key)
        if cached:
            return uuid.UUID(cached)
    except Exception:
        redis = None

    result = await db.execute(
        select(Organization.id, Organization.attora_api_key).where(
            Organization.attora_api_key.isnot(None)
        )
    )
    for row in result.all():
        try:
            if decrypt_value(row.attora_api_key) == x_attora_key:
                if redis is not None:
                    try:
                        await redis.setex(cache_key, 3600, str(row.id))
                    except Exception:
                        pass
                return row.id
        except Exception:
            continue

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
    )
