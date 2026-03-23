"""
Attora — SQLAlchemy Base & Common Mixins

Provides the declarative Base, TimestampMixin, and OrgScopedMixin
used by all models.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all Attora models."""
    pass


class TimestampMixin:
    """Adds created_at and updated_at columns to any model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class OrgScopedMixin:
    """
    Adds org_id foreign key column for multi-tenant scoping.

    All queries on org-scoped tables MUST include a WHERE org_id = :org_id filter.
    This is enforced at the application layer (no Postgres RLS).
    """

    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


# ── Enums ────────────────────────────────────────────────────

class BuyerStage(str, enum.Enum):
    """Buyer journey stage for subscribers."""
    AWARENESS = "awareness"
    CONSIDERATION = "consideration"
    INTENT = "intent"
    PURCHASE = "purchase"
    POST_PURCHASE = "post_purchase"


class ConversationStatus(str, enum.Enum):
    """Status of a conversation."""
    ACTIVE = "active"
    CONVERTED = "converted"
    STALE = "stale"
    CLOSED = "closed"


class MessageSender(str, enum.Enum):
    """Who sent the message."""
    USER = "user"
    AI = "ai"
    HUMAN = "human"


class ChannelType(str, enum.Enum):
    """Messaging channel."""
    WHATSAPP = "whatsapp"
    MESSENGER = "messenger"
    INSTAGRAM = "instagram"


class ConversionType(str, enum.Enum):
    """Type of conversion event."""
    LEAD = "lead"
    INITIATE_CHECKOUT = "initiate_checkout"
    PURCHASE = "purchase"
    UPSELL = "upsell"


class UserRole(str, enum.Enum):
    """User role within an organization."""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"
