"""
Attora — AI Config Model

Stores per-organization AI persona configuration, brand voice,
compliance rules, and conversation playbooks. One config per org (unique).
"""

import uuid

from sqlalchemy import Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScopedMixin, TimestampMixin


class AIConfig(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "ai_config"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    __table_args__ = (
        UniqueConstraint("org_id", name="uq_ai_config_org_id"),
        {"comment": "One AI config per organization"},
    )

    brand_voice: Mapped[str | None] = mapped_column(Text, nullable=True)
    persona_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_knowledge: Mapped[str | None] = mapped_column(Text, nullable=True)
    compliance_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversion_playbook: Mapped[str | None] = mapped_column(Text, nullable=True)
    objection_handlers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    greeting_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_messages_before_handoff: Mapped[int] = mapped_column(Integer, default=50, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="ai_config")

    def __repr__(self) -> str:
        return f"<AIConfig(id={self.id}, org_id={self.org_id}, persona={self.persona_name!r})>"
