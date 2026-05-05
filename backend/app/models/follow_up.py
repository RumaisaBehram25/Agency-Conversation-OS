"""
Attora — Follow-up Rule Model

One row per nudge in a campaign's sequence (e.g. four touches at
step_order 1–4).

The dispatcher (`services/follow_up_engine.py`) runs on a cron (often every
15 minutes) and sends the next eligible touch via ManyChat when timing and
silence checks pass.
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

    # Touch 1: minutes since last user message (or conversation start).
    # Touch 2+: minutes since the previous follow-up (`last_follow_up_at`).
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
