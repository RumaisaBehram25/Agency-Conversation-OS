"""
Attora — AI Config Pydantic Schemas

Request/response models for AI configuration endpoints.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AIConfigUpdate(BaseModel):
    """PUT /api/ai-config — Upsert AI configuration."""

    brand_voice: str | None = None
    persona_name: str | None = None
    product_knowledge: str | None = None
    compliance_rules: str | None = None
    conversion_playbook: str | list | None = None
    objection_handlers: dict | None = None
    greeting_message: str | None = None
    fallback_message: str | None = None
    max_messages_before_handoff: int = Field(50, ge=1, le=500)

    @model_validator(mode="after")
    def validate_objection_handlers(self) -> "AIConfigUpdate":
        """Ensure objection_handlers is a dict of {question: response} string pairs."""
        if self.objection_handlers is not None:
            if not isinstance(self.objection_handlers, dict):
                raise ValueError("objection_handlers must be a dictionary")
            for key, value in self.objection_handlers.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise ValueError(
                        "objection_handlers must be a dict of {question: response} string pairs"
                    )
        return self


class AIConfigResponse(BaseModel):
    """AI config data returned in API responses."""

    id: UUID | None = None
    org_id: UUID | None = None
    brand_voice: str | None = None
    persona_name: str | None = None
    product_knowledge: str | None = None
    compliance_rules: str | None = None
    conversion_playbook: str | list | None = None
    objection_handlers: dict | None = None
    greeting_message: str | None = None
    fallback_message: str | None = None
    max_messages_before_handoff: int = 50
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
