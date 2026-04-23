"""
Attora — Knowledge Document Model

Stores chunked knowledge base documents used by the AI engine
across all organizations. This is a GLOBAL (platform-level) table
with no org_id — it serves as Attora's shared "secret sauce" for
objection handling, sales SOPs, and messaging playbooks.
"""

import uuid
from typing import List

from sqlalchemy import Boolean, String, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── Content ─────────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Classification ──────────────────────────────────────
    keywords: Mapped[List[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )
    ad_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    section_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Status ──────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeDocument(id={self.id}, title={self.title!r}, "
            f"category={self.category!r})>"
        )
