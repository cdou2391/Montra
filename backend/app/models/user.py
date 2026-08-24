import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.db.enums import Context, UserStatus


class User(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status"), default=UserStatus.ACTIVE, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    preferences: Mapped["UserPreference"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserPreference(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    hide_balances: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    persist_balance_privacy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_context: Mapped[Context] = mapped_column(
        SAEnum(Context, name="context_type"), default=Context.PERSONAL, nullable=False
    )
    default_reminder_days: Mapped[int | None] = mapped_column(Integer, default=3)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # The favourite lives on the user, not the account. Accounts become
    # shareable in the Family phases, and a flag on the account row would make
    # one member's favourite everybody's. SET NULL so archiving or deleting the
    # account simply clears it.
    favorite_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL")
    )

    user: Mapped[User] = relationship(back_populates="preferences")


class Session(UUIDPrimaryKey, Timestamped, Base):
    """Session records live in Postgres so revocation survives a restart."""

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()
