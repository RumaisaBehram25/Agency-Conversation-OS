"""
Hyros sync run audit — per-org snapshot after each successful Hyros pull.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScopedMixin


class HyrosSyncLog(Base, OrgScopedMixin):
    __tablename__ = "hyros_sync_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    sales_scanned: Mapped[int] = mapped_column(Integer, nullable=False)
    purchases_matched: Mapped[int] = mapped_column(Integer, nullable=False)
    unmatched_sales: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_by_attora_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_by_attora_sub: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_by_email: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    organization = relationship("Organization", back_populates="hyros_sync_logs")
