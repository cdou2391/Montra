"""Household membership (Implementation Plan Phase 16).

A Family is a permission boundary, not a wallet. It owns nothing itself:
accounts and loans keep their own owner, and the family only governs who may
see and touch them.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey, utcnow
from app.db.enums import FamilyRole, FamilyStatus, InvitationStatus, MembershipStatus


class Family(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "families"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[FamilyStatus] = mapped_column(
        SAEnum(FamilyStatus, name="family_status"), default=FamilyStatus.ACTIVE, nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["FamilyMembership"]] = relationship(
        back_populates="family", cascade="all, delete-orphan"
    )


class FamilyMembership(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "family_memberships"

    family_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("families.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[FamilyRole] = mapped_column(
        SAEnum(FamilyRole, name="family_role"), default=FamilyRole.ADULT, nullable=False
    )
    status: Mapped[MembershipStatus] = mapped_column(
        SAEnum(MembershipStatus, name="membership_status"),
        default=MembershipStatus.ACTIVE,
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    family: Mapped[Family] = relationship(back_populates="memberships")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("family_id", "user_id", name="one_membership_per_family"),
        Index("ix_family_memberships_family", "family_id", "status"),
        # One ACTIVE family per user for MVP (Data Model section 9). A partial
        # unique index, so the database refuses a second active membership
        # rather than trusting the service layer to remember.
        Index(
            "uq_one_active_family_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )


class FamilyInvitation(UUIDPrimaryKey, Timestamped, Base):
    """The raw token is never stored, only its hash — same treatment as a
    session token, because an invitation grants access to household finances."""

    __tablename__ = "family_invitations"

    family_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("families.id", ondelete="CASCADE"), nullable=False
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    invitee_email: Mapped[str | None] = mapped_column(String(320), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    proposed_role: Mapped[FamilyRole] = mapped_column(
        SAEnum(FamilyRole, name="family_role"), default=FamilyRole.ADULT, nullable=False
    )
    status: Mapped[InvitationStatus] = mapped_column(
        SAEnum(InvitationStatus, name="invitation_status"),
        default=InvitationStatus.PENDING,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    family: Mapped[Family] = relationship()

    __table_args__ = (Index("ix_invitations_family_status", "family_id", "status"),)
