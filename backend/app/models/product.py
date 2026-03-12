"""
Attora — Product Model

Stores per-organization product catalog for AI conversation context.
"""

import uuid

from sqlalchemy import Boolean, Integer, Numeric, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScopedMixin, TimestampMixin


class Product(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversion_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    eligibility_criteria: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    objection_responses: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="products")

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name={self.name!r}, org_id={self.org_id})>"
