"""
Attora — User Pydantic Schemas

Response models for user data.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    """User data returned in API responses."""
    id: UUID
    email: EmailStr
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class OrgUserResponse(BaseModel):
    """Organization membership data."""
    id: UUID
    user_id: UUID
    org_id: UUID
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}
