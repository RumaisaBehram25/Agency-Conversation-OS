"""
Attora — Follow-up Rule Model

One row per nudge in a campaign's sequence. Example for the MUSCLE
campaign: three rows at step_order 1/2/3 with after_minutes 60/180/720.

The dispatcher (`services/follow_up_engine.py`) reads these rules every
~15 min and sends `messages[step_order]` via ManyChat when the subscriber
has been silent past the configured threshold and hasn't bought yet.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScopedMixin, TimestampMixin


class CampaignFollowUp(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "campaign_follow_ups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ad_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 1-indexed touch number (Touch 1, Touch 2, …). Unique per campaign so
    # the engine can fetch in order and address them by position.
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)

    # Minutes of subscriber silence before this touch fires. Measured from
    # `subscribers.last_user_message_at` (or, when the user has never
    # replied, from `conversation.started_at`).
    after_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    # The message body. May contain `[LINK]` which the engine replaces with
    # the subscriber's per-campaign UTM-tagged checkout URL at send time.
    message: Mapped[str] = mapped_column(Text, nullable=False)

    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    campaign = relationship("AdCampaign", back_populates="follow_ups")
    organization = relationship("Organization")

    __table_args__ = (
        Index(
            "uq_campaign_follow_ups_step",
            "campaign_id",
            "step_order",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CampaignFollowUp(campaign_id={self.campaign_id}, "
            f"step={self.step_order}, after={self.after_minutes}min)>"
        )
