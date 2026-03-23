"""
Attora — Organization Model

Stores multi-tenant organization data including per-client
ManyChat account credentials and Meta access credentials.
Sensitive fields (manychat_api_key, meta_capi_token, attora_api_key)
are encrypted at the application layer before storage.
"""

import uuid

from sqlalchemy import Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # ── ManyChat Configuration ───────────────────────────────
    manychat_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted
    manychat_page_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manychat_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Meta Configuration ───────────────────────────────────
    meta_pixel_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_capi_token: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted
    meta_ad_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_page_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_business_manager_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Attora API Key (for webhook auth) ────────────────────
    attora_api_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)  # encrypted

    # ── Plan & Limits ────────────────────────────────────────
    plan: Mapped[str] = mapped_column(String(50), default="starter", nullable=False)
    monthly_conversation_limit: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)

    # ── Relationships ────────────────────────────────────────
    org_users = relationship("OrgUser", back_populates="organization", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="organization", cascade="all, delete-orphan")
    ai_config = relationship("AIConfig", back_populates="organization", uselist=False, cascade="all, delete-orphan")
    subscribers = relationship("Subscriber", back_populates="organization", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="organization", cascade="all, delete-orphan")
    conversion_events = relationship("ConversionEvent", back_populates="organization", cascade="all, delete-orphan")
    daily_analytics = relationship("DailyAnalytics", back_populates="organization", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name={self.name!r}, slug={self.slug!r})>"
