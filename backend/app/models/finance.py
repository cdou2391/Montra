import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.db.enums import (
    AccountStatus,
    AccountType,
    CategoryStatus,
    CategoryType,
    Direction,
    InstitutionType,
    OwnershipType,
    TransactionStatus,
    TransactionType,
    TransferStatus,
    Visibility,
)

AMOUNT = Numeric(20, 4)


class Institution(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "institutions"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    type: Mapped[InstitutionType | None] = mapped_column(
        SAEnum(InstitutionType, name="institution_type")
    )
    country_code: Mapped[str | None] = mapped_column(String(2))


class Account(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "accounts"

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    family_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), index=True)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("institutions.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(
        SAEnum(AccountType, name="account_type"), nullable=False
    )
    ownership_type: Mapped[OwnershipType] = mapped_column(
        SAEnum(OwnershipType, name="ownership_type"),
        default=OwnershipType.PERSONAL,
        nullable=False,
    )
    visibility: Mapped[Visibility] = mapped_column(
        SAEnum(Visibility, name="visibility"), default=Visibility.PRIVATE, nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False, default=Decimal("0"))
    opening_balance_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    account_identifier: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[AccountStatus] = mapped_column(
        SAEnum(AccountStatus, name="account_status"), default=AccountStatus.ACTIVE, nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Out of the net-worth totals while still a full account: it holds a
    # balance, it transacts, and its spending still counts. For money that is
    # yours to administer but not yours to count.
    excluded_from_totals: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Credit-card fields -------------------------------------------------
    # On Account rather than their own table, and meaningful only where
    # account_type = CREDIT_CARD. A CreditCardProfile is the refactor if cards
    # grow.
    credit_limit: Mapped[Decimal | None] = mapped_column(AMOUNT)
    statement_balance: Mapped[Decimal | None] = mapped_column(AMOUNT)
    statement_closing_day: Mapped[int | None] = mapped_column(SmallInteger)
    payment_due_day: Mapped[int | None] = mapped_column(SmallInteger)
    minimum_payment: Mapped[Decimal | None] = mapped_column(AMOUNT)
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    expiry_month: Mapped[int | None] = mapped_column(SmallInteger)
    expiry_year: Mapped[int | None] = mapped_column(SmallInteger)

    institution: Mapped[Institution | None] = relationship()

    __table_args__ = (
        Index("ix_accounts_owner_status", "owner_user_id", "status"),
        CheckConstraint(
            "(owner_user_id IS NOT NULL) OR (family_id IS NOT NULL)",
            name="owner_or_family_required",
        ),
        CheckConstraint(
            "credit_limit IS NULL OR credit_limit >= 0", name="credit_limit_non_negative"
        ),
        CheckConstraint(
            "statement_closing_day IS NULL OR statement_closing_day BETWEEN 1 AND 31",
            name="statement_closing_day_range",
        ),
        CheckConstraint(
            "payment_due_day IS NULL OR payment_due_day BETWEEN 1 AND 31",
            name="payment_due_day_range",
        ),
        CheckConstraint(
            "expiry_month IS NULL OR expiry_month BETWEEN 1 AND 12", name="expiry_month_range"
        ),
    )


class Category(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "categories"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), index=True)
    parent_category_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category_type: Mapped[CategoryType] = mapped_column(
        SAEnum(CategoryType, name="category_type"), nullable=False
    )
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[CategoryStatus] = mapped_column(
        SAEnum(CategoryStatus, name="category_status"),
        default=CategoryStatus.ACTIVE,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", "category_type", name="user_category_name"),
    )


class Transfer(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "transfers"

    source_account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    destination_account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    source_amount: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False)
    destination_amount: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False)
    source_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    destination_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TransferStatus] = mapped_column(
        SAEnum(TransferStatus, name="transfer_status"),
        default=TransferStatus.COMPLETED,
        nullable=False,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "source_account_id <> destination_account_id", name="distinct_transfer_accounts"
        ),
        CheckConstraint("source_amount > 0", name="source_amount_positive"),
        CheckConstraint("destination_amount > 0", name="destination_amount_positive"),
        UniqueConstraint("created_by", "idempotency_key", name="transfer_idempotency"),
    )


class Transaction(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "transactions"

    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, name="transaction_type"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False)
    direction: Mapped[Direction] = mapped_column(
        SAEnum(Direction, name="ledger_direction"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # When the money moved, as against created_at, when it was entered.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus, name="transaction_status"),
        default=TransactionStatus.COMPLETED,
        nullable=False,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )
    merchant: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String(120))
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("transfers.id", ondelete="CASCADE"), index=True
    )
    loan_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("loan_payments.id", ondelete="CASCADE"), index=True
    )
    # A charge levied on another transaction. A transaction in its own right —
    # the money really left — and the link only says what it was charged on.
    fee_for_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    account: Mapped[Account] = relationship()
    category: Mapped[Category | None] = relationship()

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_transactions_account_occurred", "account_id", "occurred_at"),
        Index("ix_transactions_account_status_occurred", "account_id", "status", "occurred_at"),
    )


class ExchangeRate(UUIDPrimaryKey, Timestamped, Base):
    """A rate the user maintains between two currencies.

    Their override of the published number in `market_rates`, for when they
    would rather state a rate than take the feed's.

    Reporting only: a converted value never replaces an original amount.
    """

    __tablename__ = "exchange_rates"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # One unit of base buys this much quote. Eight places, because RWF→USD is
    # small enough that early rounding loses real money.
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    # The daily job refreshes what it owns and leaves a hand-entered rate
    # alone, rather than replacing it overnight.
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="MANUAL")

    __table_args__ = (
        UniqueConstraint("user_id", "base_currency", "quote_currency", name="user_currency_pair"),
        CheckConstraint("rate > 0", name="exchange_rate_positive"),
        CheckConstraint("base_currency <> quote_currency", name="exchange_rate_distinct"),
    )


class MarketRate(UUIDPrimaryKey, Timestamped, Base):
    """A published rate, shared by everyone.

    One table for the whole app: the price of a dollar does not depend on who
    is asking, so adding users or currencies costs no extra API calls. User
    overrides live in `exchange_rates`.
    """

    __tablename__ = "market_rates"

    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)

    __table_args__ = (
        UniqueConstraint("base_currency", "quote_currency", name="market_currency_pair"),
        CheckConstraint("rate > 0", name="market_rate_positive"),
        CheckConstraint("base_currency <> quote_currency", name="market_rate_distinct"),
        Index("ix_market_rates_base", "base_currency"),
    )
