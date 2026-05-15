"""Request/response schemas for outbound email helpers."""

from __future__ import annotations

import uuid
from pydantic import BaseModel, EmailStr, Field


class EmailSendRequest(BaseModel):
    subscriber_id: uuid.UUID
    to_email: EmailStr
    subject: str = Field(..., min_length=1)
    html: str = Field(..., min_length=1)
    trigger_type: str = Field(..., min_length=1)
    product_id: uuid.UUID | None = None


class EmailSendResponse(BaseModel):
    status: str
    reason: str | None = None
    resend_id: str | None = None
    error: str | None = None


class EmailSettingsUpsert(BaseModel):
    emails_enabled: bool
    max_emails_per_user_per_month: int = 4
    min_days_between_emails: int = 7
    no_response_followup_days: int = 30
    from_name: str = Field(..., min_length=1)
    from_email: EmailStr
    reply_to: EmailStr | None = None
    resend_api_key: str | None = None
