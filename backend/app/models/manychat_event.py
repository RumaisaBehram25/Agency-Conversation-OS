"""
Attora — ManyChat Event Model

Stores webhook-derived ManyChat delivery lifecycle events.
"""

import uuid

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ManyChatEvent(Base, TimestampMixin):
    __tablename__ = "manychat_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    manychat_subscriber_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    flow_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    __table_args__ = (
        Index("ix_manychat_events_org_flow_type", "org_id", "flow_id", "event_type"),
    )

