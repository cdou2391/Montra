"""Backup and restore.

Not in the API specification — added on request, and the natural counterpart to
profile reset.

Two decisions shape this module:

*Restore replaces, it does not merge.* Merging two financial histories means
guessing which records are the same, and a wrong guess either duplicates money
or silently drops it. Replacing is the only outcome a user can reason about.

*Every identifier is regenerated on import.* Keeping the original UUIDs would
be simpler, but a backup restored into a different account would collide with
the rows it was exported from. Instead each old id is mapped to a fresh one and
every reference is resolved through that map — so a backup is portable, and
restoring the same file twice is not a corruption risk.

Never exported: password hashes, session tokens.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import ValidationFailed
from app.db.base import utcnow
from app.models.finance import Account, Category, Institution, Transaction, Transfer
from app.models.loans import Loan, LoanPayment
from app.models.planning import PlannedTransaction, RecurringRule, Reminder
from app.models.user import User, UserPreference
from app.services.profile import reset_profile

BACKUP_VERSION = 1

# Explicit allowlists. Exporting by field name rather than dumping the model
# keeps secrets out by construction, and means a new column cannot silently
# start appearing in people's backup files.
ACCOUNT_FIELDS = (
    "name",
    "account_type",
    "ownership_type",
    "visibility",
    "currency",
    "opening_balance",
    "opening_balance_at",
    "account_identifier",
    "description",
    "status",
    "archived_at",
    "credit_limit",
    "statement_balance",
    "statement_closing_day",
    "payment_due_day",
    "minimum_payment",
    "interest_rate",
    "expiry_month",
    "expiry_year",
)
TRANSACTION_FIELDS = (
    "transaction_type",
    "amount",
    "direction",
    "currency",
    "occurred_at",
    "status",
    "merchant",
    "description",
    "notes",
    "reference",
    "deleted_at",
)
TRANSFER_FIELDS = (
    "source_amount",
    "destination_amount",
    "source_currency",
    "destination_currency",
    "occurred_at",
    "notes",
    "status",
    "cancelled_at",
)
CATEGORY_FIELDS = ("name", "category_type", "is_system", "status")
INSTITUTION_FIELDS = ("name", "type", "country_code")
RULE_FIELDS = (
    "planned_type",
    "amount",
    "currency",
    "name",
    "notes",
    "frequency",
    "interval_value",
    "start_date",
    "end_date",
    "next_occurrence_date",
    "occurrence_hour",
    "reminder_days_before",
    "status",
)
PLANNED_FIELDS = (
    "planned_type",
    "amount",
    "currency",
    "expected_at",
    "occurrence_date",
    "description",
    "notes",
    "status",
    "source",
    "original_expected_at",
)
LOAN_FIELDS = (
    "direction",
    "visibility",
    "ownership_type",
    "name",
    "counterparty",
    "currency",
    "original_principal",
    "opening_outstanding_principal",
    "interest_rate",
    "start_date",
    "end_date",
    "expected_payment_amount",
    "payment_frequency",
    "next_payment_date",
    "status",
    "notes",
)
LOAN_PAYMENT_FIELDS = (
    "payment_date",
    "total_amount",
    "principal_amount",
    "interest_amount",
    "fee_amount",
    "notes",
)
REMINDER_FIELDS = ("entity_type", "remind_at", "status", "delivered_at")
PREFERENCE_FIELDS = (
    "hide_balances",
    "persist_balance_privacy",
    "default_context",
    "default_reminder_days",
    "notifications_enabled",
)


# ---------------------------------------------------------------------- export


def _dump(row: Any, fields: tuple[str, ...]) -> dict:
    out: dict[str, Any] = {"id": str(row.id)}
    for field in fields:
        value = getattr(row, field)
        if isinstance(value, Decimal):
            out[field] = str(value)
        elif isinstance(value, datetime | date):
            out[field] = value.isoformat()
        elif hasattr(value, "value"):  # StrEnum
            out[field] = value.value
        else:
            out[field] = value
    return out


def export_backup(db: DbSession, user: User) -> dict:
    """Everything this user owns, in one portable document."""
    account_ids = select(Account.id).where(Account.owner_user_id == user.id)

    accounts = list(db.scalars(select(Account).where(Account.owner_user_id == user.id)))
    institutions = list(db.scalars(select(Institution).where(Institution.user_id == user.id)))
    categories = list(db.scalars(select(Category).where(Category.user_id == user.id)))
    transfers = list(db.scalars(select(Transfer).where(Transfer.created_by == user.id)))
    transactions = list(
        db.scalars(select(Transaction).where(Transaction.account_id.in_(account_ids)))
    )
    rules = list(db.scalars(select(RecurringRule).where(RecurringRule.created_by == user.id)))
    planned = list(
        db.scalars(select(PlannedTransaction).where(PlannedTransaction.created_by == user.id))
    )
    loans = list(db.scalars(select(Loan).where(Loan.owner_user_id == user.id)))
    payments = list(db.scalars(select(LoanPayment).where(LoanPayment.created_by == user.id)))
    reminders = list(db.scalars(select(Reminder).where(Reminder.user_id == user.id)))
    preferences = db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))

    def link(value: uuid.UUID | None) -> str | None:
        return str(value) if value else None

    return {
        "montra_backup_version": BACKUP_VERSION,
        "exported_at": utcnow().isoformat(),
        # Identifying detail only, for the restore screen to show. Never a
        # password hash or a session token.
        "user": {
            "email": user.email,
            "display_name": user.display_name,
            "base_currency": user.base_currency,
            "timezone": user.timezone,
        },
        "preferences": (
            {f: getattr(preferences, f) for f in PREFERENCE_FIELDS} if preferences else None
        ),
        "institutions": [_dump(i, INSTITUTION_FIELDS) for i in institutions],
        "categories": [
            {**_dump(c, CATEGORY_FIELDS), "parent_category_id": link(c.parent_category_id)}
            for c in categories
        ],
        "accounts": [
            {**_dump(a, ACCOUNT_FIELDS), "institution_id": link(a.institution_id)} for a in accounts
        ],
        "loans": [_dump(loan, LOAN_FIELDS) for loan in loans],
        "transfers": [
            {
                **_dump(t, TRANSFER_FIELDS),
                "source_account_id": link(t.source_account_id),
                "destination_account_id": link(t.destination_account_id),
            }
            for t in transfers
        ],
        "loan_payments": [
            {
                **_dump(p, LOAN_PAYMENT_FIELDS),
                "loan_id": link(p.loan_id),
                "account_id": link(p.account_id),
            }
            for p in payments
        ],
        "transactions": [
            {
                **_dump(t, TRANSACTION_FIELDS),
                "account_id": link(t.account_id),
                "category_id": link(t.category_id),
                "transfer_id": link(t.transfer_id),
                "loan_payment_id": link(t.loan_payment_id),
            }
            for t in transactions
        ],
        "recurring_rules": [
            {
                **_dump(r, RULE_FIELDS),
                "account_id": link(r.account_id),
                "category_id": link(r.category_id),
            }
            for r in rules
        ],
        "planned_transactions": [
            {
                **_dump(p, PLANNED_FIELDS),
                "account_id": link(p.account_id),
                "category_id": link(p.category_id),
                "recurring_rule_id": link(p.recurring_rule_id),
                "completed_transaction_id": link(p.completed_transaction_id),
            }
            for p in planned
        ],
        "reminders": [
            {**_dump(r, REMINDER_FIELDS), "entity_id": link(r.entity_id)} for r in reminders
        ],
    }


def summarize(payload: dict) -> dict:
    """Counts for the restore screen, so the user sees what they are about to
    bring in before it replaces what they have."""
    return {
        key: len(payload.get(key) or [])
        for key in (
            "accounts",
            "transactions",
            "transfers",
            "loans",
            "loan_payments",
            "planned_transactions",
            "recurring_rules",
            "categories",
        )
    }


# --------------------------------------------------------------------- restore


class _Mapper:
    """Old identifier to new identifier, resolved only through here.

    A reference that is not in the map is dropped rather than guessed at, so a
    malformed file cannot attach a transaction to somebody else's account.
    """

    def __init__(self) -> None:
        self._map: dict[str, uuid.UUID] = {}

    def issue(self, old: str | None) -> uuid.UUID:
        new = uuid.uuid4()
        if old:
            self._map[str(old)] = new
        return new

    def get(self, old: Any) -> uuid.UUID | None:
        if not old:
            return None
        return self._map.get(str(old))


def _decimal(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationFailed(
            "The backup file is not valid.",
            code="INVALID_BACKUP",
            details=[{"field": field, "message": f"{value!r} is not a valid amount."}],
        ) from exc


def _dt(value: Any, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationFailed(
            "The backup file is not valid.",
            code="INVALID_BACKUP",
            details=[{"field": field, "message": f"{value!r} is not a valid timestamp."}],
        ) from exc


def _d(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationFailed(
            "The backup file is not valid.",
            code="INVALID_BACKUP",
            details=[{"field": field, "message": f"{value!r} is not a valid date."}],
        ) from exc


def validate_payload(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise ValidationFailed("That file is not a Montra backup.", code="INVALID_BACKUP")
    version = payload.get("montra_backup_version")
    if version != BACKUP_VERSION:
        raise ValidationFailed(
            f"This backup is version {version!r}; this version of Montra reads "
            f"version {BACKUP_VERSION}.",
            code="UNSUPPORTED_BACKUP_VERSION",
        )
    for key in ("accounts", "transactions", "categories"):
        if key in payload and not isinstance(payload[key], list):
            raise ValidationFailed(
                "That file is not a Montra backup.",
                code="INVALID_BACKUP",
                details=[{"field": key, "message": "Expected a list."}],
            )
    return payload


def restore_backup(db: DbSession, *, user: User, payload: dict, password: str) -> dict:
    """Replace everything this user owns with the contents of a backup.

    Runs inside the caller's transaction, so a file that fails validation
    half-way leaves the existing data untouched rather than half-replaced.
    """
    validate_payload(payload)

    # Same bar as reset: this destroys the current data, so it re-authenticates.
    reset_profile(db, user=user, password=password)

    # The default categories reset_profile just created would otherwise sit
    # alongside the ones in the backup.
    db.query(Category).filter(Category.user_id == user.id).delete()
    db.flush()

    ids = _Mapper()
    rows = lambda key: payload.get(key) or []  # noqa: E731

    for item in rows("institutions"):
        db.add(
            Institution(
                id=ids.issue(item.get("id")),
                user_id=user.id,
                name=item.get("name") or "Unnamed",
                type=item.get("type"),
                country_code=item.get("country_code"),
            )
        )
    db.flush()

    # Two passes: a child category may appear before its parent in the file.
    for item in rows("categories"):
        db.add(
            Category(
                id=ids.issue(item.get("id")),
                user_id=user.id,
                name=item.get("name") or "Unnamed",
                category_type=item.get("category_type"),
                is_system=bool(item.get("is_system")),
                status=item.get("status") or "ACTIVE",
            )
        )
    db.flush()
    for item in rows("categories"):
        parent = ids.get(item.get("parent_category_id"))
        if parent is not None:
            db.get(Category, ids.get(item.get("id"))).parent_category_id = parent

    for item in rows("accounts"):
        db.add(
            Account(
                id=ids.issue(item.get("id")),
                owner_user_id=user.id,
                created_by=user.id,
                institution_id=ids.get(item.get("institution_id")),
                name=item.get("name") or "Unnamed",
                account_type=item.get("account_type"),
                ownership_type=item.get("ownership_type") or "PERSONAL",
                visibility=item.get("visibility") or "PRIVATE",
                currency=item.get("currency") or user.base_currency,
                opening_balance=_decimal(item.get("opening_balance", 0), "opening_balance"),
                opening_balance_at=_dt(item.get("opening_balance_at"), "opening_balance_at")
                or utcnow(),
                account_identifier=item.get("account_identifier"),
                description=item.get("description"),
                status=item.get("status") or "ACTIVE",
                archived_at=_dt(item.get("archived_at"), "archived_at"),
                credit_limit=(
                    _decimal(item["credit_limit"], "credit_limit")
                    if item.get("credit_limit") is not None
                    else None
                ),
                statement_balance=(
                    _decimal(item["statement_balance"], "statement_balance")
                    if item.get("statement_balance") is not None
                    else None
                ),
                statement_closing_day=item.get("statement_closing_day"),
                payment_due_day=item.get("payment_due_day"),
                minimum_payment=(
                    _decimal(item["minimum_payment"], "minimum_payment")
                    if item.get("minimum_payment") is not None
                    else None
                ),
                interest_rate=(
                    _decimal(item["interest_rate"], "interest_rate")
                    if item.get("interest_rate") is not None
                    else None
                ),
                expiry_month=item.get("expiry_month"),
                expiry_year=item.get("expiry_year"),
            )
        )
    db.flush()

    for item in rows("loans"):
        db.add(
            Loan(
                id=ids.issue(item.get("id")),
                owner_user_id=user.id,
                created_by=user.id,
                direction=item.get("direction"),
                visibility=item.get("visibility") or "PRIVATE",
                ownership_type=item.get("ownership_type") or "PERSONAL",
                name=item.get("name") or "Unnamed",
                counterparty=item.get("counterparty"),
                currency=item.get("currency") or user.base_currency,
                original_principal=_decimal(
                    item.get("original_principal", 0), "original_principal"
                ),
                opening_outstanding_principal=_decimal(
                    item.get("opening_outstanding_principal", 0),
                    "opening_outstanding_principal",
                ),
                interest_rate=(
                    _decimal(item["interest_rate"], "interest_rate")
                    if item.get("interest_rate") is not None
                    else None
                ),
                start_date=_d(item.get("start_date"), "start_date") or utcnow().date(),
                end_date=_d(item.get("end_date"), "end_date"),
                expected_payment_amount=(
                    _decimal(item["expected_payment_amount"], "expected_payment_amount")
                    if item.get("expected_payment_amount") is not None
                    else None
                ),
                payment_frequency=item.get("payment_frequency"),
                next_payment_date=_d(item.get("next_payment_date"), "next_payment_date"),
                status=item.get("status") or "ACTIVE",
                notes=item.get("notes"),
            )
        )
    db.flush()

    for item in rows("transfers"):
        source = ids.get(item.get("source_account_id"))
        destination = ids.get(item.get("destination_account_id"))
        if source is None or destination is None:
            continue  # A transfer with a missing side is not a transfer.
        db.add(
            Transfer(
                id=ids.issue(item.get("id")),
                created_by=user.id,
                source_account_id=source,
                destination_account_id=destination,
                source_amount=_decimal(item.get("source_amount", 0), "source_amount"),
                destination_amount=_decimal(
                    item.get("destination_amount", 0), "destination_amount"
                ),
                source_currency=item.get("source_currency") or user.base_currency,
                destination_currency=item.get("destination_currency") or user.base_currency,
                occurred_at=_dt(item.get("occurred_at"), "occurred_at") or utcnow(),
                notes=item.get("notes"),
                status=item.get("status") or "COMPLETED",
                cancelled_at=_dt(item.get("cancelled_at"), "cancelled_at"),
            )
        )
    db.flush()

    for item in rows("loan_payments"):
        loan_id = ids.get(item.get("loan_id"))
        account_id = ids.get(item.get("account_id"))
        if loan_id is None or account_id is None:
            continue
        db.add(
            LoanPayment(
                id=ids.issue(item.get("id")),
                created_by=user.id,
                loan_id=loan_id,
                account_id=account_id,
                payment_date=_d(item.get("payment_date"), "payment_date") or utcnow().date(),
                total_amount=_decimal(item.get("total_amount", 0), "total_amount"),
                principal_amount=_decimal(item.get("principal_amount", 0), "principal_amount"),
                interest_amount=_decimal(item.get("interest_amount", 0), "interest_amount"),
                fee_amount=_decimal(item.get("fee_amount", 0), "fee_amount"),
                notes=item.get("notes"),
            )
        )
    db.flush()

    for item in rows("transactions"):
        account_id = ids.get(item.get("account_id"))
        if account_id is None:
            continue  # A ledger entry with no account cannot be placed.
        db.add(
            Transaction(
                id=ids.issue(item.get("id")),
                created_by=user.id,
                account_id=account_id,
                category_id=ids.get(item.get("category_id")),
                transfer_id=ids.get(item.get("transfer_id")),
                loan_payment_id=ids.get(item.get("loan_payment_id")),
                transaction_type=item.get("transaction_type"),
                amount=_decimal(item.get("amount", 0), "amount"),
                direction=item.get("direction"),
                currency=item.get("currency") or user.base_currency,
                occurred_at=_dt(item.get("occurred_at"), "occurred_at") or utcnow(),
                status=item.get("status") or "COMPLETED",
                merchant=item.get("merchant"),
                description=item.get("description"),
                notes=item.get("notes"),
                reference=item.get("reference"),
                deleted_at=_dt(item.get("deleted_at"), "deleted_at"),
            )
        )
    db.flush()

    for item in rows("recurring_rules"):
        account_id = ids.get(item.get("account_id"))
        if account_id is None:
            continue
        db.add(
            RecurringRule(
                id=ids.issue(item.get("id")),
                created_by=user.id,
                account_id=account_id,
                category_id=ids.get(item.get("category_id")),
                planned_type=item.get("planned_type"),
                amount=_decimal(item.get("amount", 0), "amount"),
                currency=item.get("currency") or user.base_currency,
                name=item.get("name") or "Unnamed",
                notes=item.get("notes"),
                frequency=item.get("frequency"),
                interval_value=int(item.get("interval_value") or 1),
                start_date=_d(item.get("start_date"), "start_date") or utcnow().date(),
                end_date=_d(item.get("end_date"), "end_date"),
                next_occurrence_date=_d(item.get("next_occurrence_date"), "next_occurrence_date"),
                occurrence_hour=int(item.get("occurrence_hour") or 9),
                reminder_days_before=item.get("reminder_days_before"),
                status=item.get("status") or "ACTIVE",
            )
        )
    db.flush()

    for item in rows("planned_transactions"):
        account_id = ids.get(item.get("account_id"))
        if account_id is None:
            continue
        db.add(
            PlannedTransaction(
                id=ids.issue(item.get("id")),
                created_by=user.id,
                account_id=account_id,
                category_id=ids.get(item.get("category_id")),
                recurring_rule_id=ids.get(item.get("recurring_rule_id")),
                completed_transaction_id=ids.get(item.get("completed_transaction_id")),
                planned_type=item.get("planned_type"),
                amount=_decimal(item.get("amount", 0), "amount"),
                currency=item.get("currency") or user.base_currency,
                expected_at=_dt(item.get("expected_at"), "expected_at") or utcnow(),
                occurrence_date=_d(item.get("occurrence_date"), "occurrence_date")
                or utcnow().date(),
                description=item.get("description") or "Restored item",
                notes=item.get("notes"),
                status=item.get("status") or "UPCOMING",
                source=item.get("source") or "ONE_TIME",
                original_expected_at=_dt(item.get("original_expected_at"), "original_expected_at"),
            )
        )
    db.flush()

    for item in rows("reminders"):
        entity_id = ids.get(item.get("entity_id"))
        if entity_id is None:
            continue  # A reminder pointing at nothing would never fire usefully.
        db.add(
            Reminder(
                id=ids.issue(item.get("id")),
                user_id=user.id,
                entity_type=item.get("entity_type") or "PLANNED_TRANSACTION",
                entity_id=entity_id,
                remind_at=_dt(item.get("remind_at"), "remind_at") or utcnow(),
                status=item.get("status") or "PENDING",
                delivered_at=_dt(item.get("delivered_at"), "delivered_at"),
            )
        )

    preferences_payload = payload.get("preferences")
    if isinstance(preferences_payload, dict):
        preferences = db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
        if preferences is not None:
            for field in PREFERENCE_FIELDS:
                if field in preferences_payload and preferences_payload[field] is not None:
                    setattr(preferences, field, preferences_payload[field])

    db.flush()
    return summarize(payload)
