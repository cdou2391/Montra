"""Forward-looking finance: planned transactions, recurrence, reminders and
notifications (Implementation Plan Phases 11-14).

The governing rule, from Phase 11:

    Planned transaction != ledger transaction

until completion. Nothing in this module writes to a balance; completion hands
off to the posting engine.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey, utcnow
from app.db.enums import (
    Frequency,
    NotificationType,
    PlannedSource,
    PlannedStatus,
    PlannedType,
    RecurringStatus,
    ReminderEntity,
    ReminderStatus,
)

AMOUNT = Numeric(20, 4)


class RecurringRule(UUIDPrimaryKey, Timestamped, Base):
    """A template that generates planned occurrences. Never a ledger entry."""

    __tablename__ = "recurring_rules"

    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    planned_type: Mapped[PlannedType] = mapped_column(
        SAEnum(PlannedType, name="planned_type"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    frequency: Mapped[Frequency] = mapped_column(
        SAEnum(Frequency, name="recurrence_frequency"), nullable=False
    )
    interval_value: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    next_occurrence_date: Mapped[date | None] = mapped_column(Date, index=True)

    # Time of day to stamp on generated occurrences, in the owner's timezone.
    occurrence_hour: Mapped[int] = mapped_column(Integer, default=9, nullable=False)
    reminder_days_before: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[RecurringStatus] = mapped_column(
        SAEnum(RecurringStatus, name="recurring_status"),
        default=RecurringStatus.ACTIVE,
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="recurring_amount_positive"),
        CheckConstraint("interval_value >= 1", name="interval_at_least_one"),
        CheckConstraint("occurrence_hour BETWEEN 0 AND 23", name="occurrence_hour_range"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="end_after_start"),
        Index("ix_recurring_status_next", "status", "next_occurrence_date"),
    )


class PlannedTransaction(UUIDPrimaryKey, Timestamped, Base):
    """An expected future movement. Carries no ledger effect until completed."""

    __tablename__ = "planned_transactions"

    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    planned_type: Mapped[PlannedType] = mapped_column(
        SAEnum(PlannedType, name="planned_type"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    expected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # The local calendar day of expected_at, frozen at write time. Carries the
    # documented uniqueness constraint for recurrence and keeps day-grouping
    # queries off a timezone conversion.
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False)

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    status: Mapped[PlannedStatus] = mapped_column(
        SAEnum(PlannedStatus, name="planned_status"),
        default=PlannedStatus.UPCOMING,
        nullable=False,
    )
    source: Mapped[PlannedSource] = mapped_column(
        SAEnum(PlannedSource, name="planned_source"),
        default=PlannedSource.ONE_TIME,
        nullable=False,
    )

    recurring_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("recurring_rules.id", ondelete="CASCADE"), index=True
    )
    completed_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL")
    )
    original_expected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Set on the first successful completion. A replayed key returns the same
    # planned item rather than posting twice.
    completion_key: Mapped[str | None] = mapped_column(String(255))

    created_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    account = relationship("Account")
    category = relationship("Category")
    rule: Mapped[RecurringRule | None] = relationship()

    __table_args__ = (
        CheckConstraint("amount > 0", name="planned_amount_positive"),
        # The documented duplicate guard: one occurrence per rule per day.
        UniqueConstraint(
            "recurring_rule_id", "occurrence_date", name="one_occurrence_per_rule_per_day"
        ),
        Index("ix_planned_account_expected", "account_id", "expected_at"),
        Index("ix_planned_status_expected", "status", "expected_at"),
    )


class Reminder(UUIDPrimaryKey, Timestamped, Base):
    """One row per recipient (Data Model section 38).

    Reminder definitions live in Postgres, never only in the Celery queue, so a
    lost broker cannot lose a reminder (Implementation Plan Phase 13).
    """

    __tablename__ = "reminders"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[ReminderEntity] = mapped_column(
        SAEnum(ReminderEntity, name="reminder_entity"), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ReminderStatus] = mapped_column(
        SAEnum(ReminderStatus, name="reminder_status"),
        default=ReminderStatus.PENDING,
        nullable=False,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_reminders_due", "status", "remind_at"),)


class Notification(UUIDPrimaryKey, Base):
    """In-app notification. Never carries another member's private detail."""

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, name="notification_type"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    related_entity_type: Mapped[ReminderEntity | None] = mapped_column(
        SAEnum(ReminderEntity, name="reminder_entity")
    )
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "read_at"),)
