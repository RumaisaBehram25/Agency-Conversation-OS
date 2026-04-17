"""
Attora — Product Pydantic Schemas

Request/response models for product CRUD endpoints.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    """POST /api/products — Create a new product."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    price: float | None = Field(None, ge=0)
    currency: str = Field("USD", max_length=10)
    checkout_url: str | None = None
    conversion_value: float | None = Field(None, ge=0)
    eligibility_criteria: dict | None = None
    objection_responses: dict | None = None
    is_active: bool = True
    sort_order: int = 0


class ProductUpdate(BaseModel):
    """PUT /api/products/{id} — Update product fields."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    price: float | None = Field(None, ge=0)
    currency: str | None = Field(None, max_length=10)
    checkout_url: str | None = None
    conversion_value: float | None = Field(None, ge=0)
    eligibility_criteria: dict | None = None
    objection_responses: dict | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class ProductResponse(BaseModel):
    """Product data returned in API responses."""

    id: UUID
    org_id: UUID
    name: str
    description: str | None = None
    price: float | None = None
    currency: str
    checkout_url: str | None = None
    conversion_value: float | None = None
    eligibility_criteria: dict | None = None
    objection_responses: dict | None = None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
