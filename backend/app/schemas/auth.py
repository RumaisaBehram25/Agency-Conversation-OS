"""
Attora — Auth Pydantic Schemas

Request/response models for authentication endpoints.
"""

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """POST /api/auth/register — Create a new user account."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """POST /api/auth/login — Authenticate with email/password."""
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """POST /api/auth/refresh — Exchange refresh token for new access token."""
    refresh_token: str


class TokenResponse(BaseModel):
    """Token pair returned on successful auth."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(TokenResponse):
    """Login response with user info."""
    user_id: str
    email: str
