"""Loans and loan payments.

A loan is not an Account. It carries its own outstanding principal, derived
from its opening figure minus the principal actually paid off, so the original
loan amount is never overwritten.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.db.enums import (
    Frequency,
    LoanDirection,
    LoanStatus,
    OwnershipType,
    Visibility,
)

AMOUNT = Numeric(20, 4)


class Loan(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "loans"

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    family_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), index=True)
    direction: Mapped[LoanDirection] = mapped_column(
        SAEnum(LoanDirection, name="loan_direction"), nullable=False
    )
    visibility: Mapped[Visibility] = mapped_column(
        SAEnum(Visibility, name="visibility"), default=Visibility.PRIVATE, nullable=False
    )
    ownership_type: Mapped[OwnershipType] = mapped_column(
        SAEnum(OwnershipType, name="ownership_type"),
        default=OwnershipType.PERSONAL,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    counterparty: Mapped[str | None] = mapped_column(String(160))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    original_principal: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False)
    # Kept separate from original_principal so a loan taken on part-way through
    # its life still reports progress honestly.
    opening_outstanding_principal: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False)

    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    expected_payment_amount: Mapped[Decimal | None] = mapped_column(AMOUNT)
    payment_frequency: Mapped[Frequency | None] = mapped_column(
        SAEnum(Frequency, name="recurrence_frequency")
    )
    next_payment_date: Mapped[date | None] = mapped_column(Date)

    status: Mapped[LoanStatus] = mapped_column(
        SAEnum(LoanStatus, name="loan_status"), default=LoanStatus.ACTIVE, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    payments: Mapped[list["LoanPayment"]] = relationship(
        back_populates="loan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("original_principal >= 0", name="original_principal_non_negative"),
        CheckConstraint(
            "opening_outstanding_principal >= 0", name="opening_outstanding_non_negative"
        ),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="loan_end_after_start"),
        Index("ix_loans_owner_status", "owner_user_id", "status"),
    )


class LoanPayment(UUIDPrimaryKey, Timestamped, Base):
    """One payment, split across principal, interest and fees.

    The split is the whole point: only the principal portion moves the loan
    balance, while interest and fees are real income or expense.
    """

    __tablename__ = "loan_payments"

    loan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("loans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)

    total_amount: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False)
    principal_amount: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False)
    interest_amount: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False, default=Decimal("0"))
    fee_amount: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False, default=Decimal("0"))

    notes: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    loan: Mapped[Loan] = relationship(back_populates="payments")

    __table_args__ = (
        CheckConstraint("total_amount > 0", name="loan_payment_total_positive"),
        CheckConstraint("principal_amount >= 0", name="loan_principal_non_negative"),
        CheckConstraint("interest_amount >= 0", name="loan_interest_non_negative"),
        CheckConstraint("fee_amount >= 0", name="loan_fee_non_negative"),
        # The allocation must account for every unit of the payment.
        CheckConstraint(
            "principal_amount + interest_amount + fee_amount = total_amount",
            name="loan_payment_allocation_balances",
        ),
        UniqueConstraint("created_by", "idempotency_key", name="loan_payment_idempotency"),
        Index("ix_loan_payments_loan_date", "loan_id", "payment_date"),
    )
