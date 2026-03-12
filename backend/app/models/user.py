"""
Attora — User & OrgUser Models

User: Authentication table with email/password.
OrgUser: Many-to-many membership linking users to organizations with roles.
"""

import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UserRole


class User(Base, TimestampMixin):
    """
    Authentication user. Stores credentials for dashboard access.
    A user can belong to multiple organizations via OrgUser.
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    org_memberships = relationship("OrgUser", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email!r})>"


class OrgUser(Base, TimestampMixin):
    """
    Organization membership. Links a User to an Organization with a role.
    Enforces unique (user_id, org_id) constraint.
    """
    __tablename__ = "org_users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda x: [e.value for e in x]),
        default=UserRole.MEMBER,
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="org_memberships")
    organization = relationship("Organization", back_populates="org_users")

    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_org_users_user_org"),
    )

    def __repr__(self) -> str:
        return f"<OrgUser(user_id={self.user_id}, org_id={self.org_id}, role={self.role})>"
