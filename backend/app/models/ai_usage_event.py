"""
Attora — AI Usage Event Model

One row per Anthropic API call in the live message pipeline. Tracks
input/output tokens plus cache read/write tokens per stage (classifier
or response generation) so per-org LLM cost can be computed accurately.
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScopedMixin, TimestampMixin


class AIUsageEvent(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "ai_usage_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )

    stage: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<AIUsageEvent(org_id={self.org_id}, stage={self.stage}, "
            f"model={self.model}, in={self.input_tokens}, out={self.output_tokens})>"
        )
