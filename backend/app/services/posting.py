"""The financial posting engine.

Every balance-moving operation goes through this service; routes never construct
a Transaction or mutate a balance directly.

Its one job is turning an *operation* plus an account's *nature* into a
`direction`, defined against that account's own balance scale: INCREASE means
its balance goes up — asset value up, or debt owed up.

Deliberately not double-entry: no contra accounts, and only a transfer writes
two entries.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, ValidationFailed
from app.db.enums import (
    AccountNature,
    Direction,
    TransactionStatus,
    TransactionType,
    TransferStatus,
    nature_for,
)
from app.models.finance import Account, Transaction, Transfer


class Operation(StrEnum):
    """A financial operation, independent of which account nature it lands on."""

    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    TRANSFER_OUT = "TRANSFER_OUT"
    TRANSFER_IN = "TRANSFER_IN"


# The entire accounting rulebook: this operation, on an account of this nature,
# moves that account's own balance in this direction.
DIRECTION_RULES: dict[tuple[Operation, AccountNature], Direction] = {
    (Operation.INCOME, AccountNature.ASSET): Direction.INCREASE,
    # A refund against a card: debt falls.
    (Operation.INCOME, AccountNature.LIABILITY): Direction.DECREASE,
    (Operation.EXPENSE, AccountNature.ASSET): Direction.DECREASE,
    # A card purchase moves no cash; it borrows more.
    (Operation.EXPENSE, AccountNature.LIABILITY): Direction.INCREASE,
    (Operation.TRANSFER_OUT, AccountNature.ASSET): Direction.DECREASE,
    # A cash advance borrows more.
    (Operation.TRANSFER_OUT, AccountNature.LIABILITY): Direction.INCREASE,
    (Operation.TRANSFER_IN, AccountNature.ASSET): Direction.INCREASE,
    # Money arriving at a card is a repayment: debt falls.
    (Operation.TRANSFER_IN, AccountNature.LIABILITY): Direction.DECREASE,
}


def resolve_direction(operation: Operation, nature: AccountNature) -> Direction:
    return DIRECTION_RULES[(operation, nature)]


@dataclass(frozen=True)
class Posting:
    """One ledger entry the engine intends to write."""

    account: Account
    operation: Operation
    amount: Decimal
    transaction_type: TransactionType

    @property
    def direction(self) -> Direction:
        return resolve_direction(self.operation, nature_for(self.account.account_type))


class PostingService:
    """Creates ledger entries and derives balances. A service or unit of work
    owns the commit, never a route."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _require_positive(amount: Decimal, field: str = "amount") -> None:
        if amount <= 0:
            raise ValidationFailed(
                details=[{"field": field, "message": "Amount must be greater than zero."}]
            )

    @staticmethod
    def _require_currency_match(account: Account, currency: str) -> None:
        if currency.upper() != account.currency.upper():
            raise ValidationFailed(
                details=[
                    {
                        "field": "currency",
                        "message": (
                            f"Transaction currency must match the account currency "
                            f"({account.currency})."
                        ),
                    }
                ]
            )

    def _write(
        self,
        posting: Posting,
        *,
        actor_id: uuid.UUID,
        occurred_at: datetime,
        category_id: uuid.UUID | None = None,
        description: str | None = None,
        merchant: str | None = None,
        notes: str | None = None,
        reference: str | None = None,
        transfer_id: uuid.UUID | None = None,
        loan_payment_id: uuid.UUID | None = None,
        fee_for_transaction_id: uuid.UUID | None = None,
        status: TransactionStatus = TransactionStatus.COMPLETED,
    ) -> Transaction:
        self._require_positive(posting.amount)
        txn = Transaction(
            account_id=posting.account.id,
            transaction_type=posting.transaction_type,
            amount=posting.amount,
            direction=posting.direction,
            currency=posting.account.currency,
            occurred_at=occurred_at,
            status=status,
            category_id=category_id,
            description=description,
            merchant=merchant,
            notes=notes,
            reference=reference,
            transfer_id=transfer_id,
            loan_payment_id=loan_payment_id,
            fee_for_transaction_id=fee_for_transaction_id,
            created_by=actor_id,
        )
        self.db.add(txn)
        self.db.flush()
        return txn

    # ------------------------------------------------------------ operations

    def record_income(
        self,
        *,
        account: Account,
        amount: Decimal,
        currency: str,
        occurred_at: datetime,
        actor_id: uuid.UUID,
        **fields,
    ) -> Transaction:
        self._require_currency_match(account, currency)
        return self._write(
            Posting(account, Operation.INCOME, amount, TransactionType.INCOME),
            actor_id=actor_id,
            occurred_at=occurred_at,
            **fields,
        )

    def record_expense(
        self,
        *,
        account: Account,
        amount: Decimal,
        currency: str,
        occurred_at: datetime,
        actor_id: uuid.UUID,
        **fields,
    ) -> Transaction:
        """Also the card-purchase path: on a LIABILITY account this raises debt
        rather than lowering cash, with no branching at the call site."""
        self._require_currency_match(account, currency)
        return self._write(
            Posting(account, Operation.EXPENSE, amount, TransactionType.EXPENSE),
            actor_id=actor_id,
            occurred_at=occurred_at,
            **fields,
        )

    def transfer_funds(
        self,
        *,
        source: Account,
        destination: Account,
        source_amount: Decimal,
        destination_amount: Decimal,
        occurred_at: datetime,
        actor_id: uuid.UUID,
        notes: str | None = None,
        idempotency_key: str | None = None,
        fee_amount: Decimal | None = None,
        fee_category_id: uuid.UUID | None = None,
    ) -> Transfer:
        """Create a transfer and both of its ledger entries.

        Not always one INCREASE and one DECREASE: a card repayment decreases
        both sides, the asset losing value and the liability losing debt.
        Direction is derived per side from that side's nature.
        """
        if source.id == destination.id:
            raise ValidationFailed(
                details=[
                    {
                        "field": "destination_account_id",
                        "message": "Source and destination must be different accounts.",
                    }
                ]
            )
        self._require_positive(source_amount, "source_amount")
        self._require_positive(destination_amount, "destination_amount")
        if fee_amount is not None:
            self._require_positive(fee_amount, "fee_amount")

        # Same-currency only for now; the columns carry both sides already.
        if source.currency != destination.currency:
            raise ValidationFailed(
                "Cross-currency transfers are not supported yet.",
                code="CURRENCY_MISMATCH",
                details=[
                    {
                        "field": "destination_account_id",
                        "message": "Both accounts must use the same currency.",
                    }
                ],
            )
        if source_amount != destination_amount:
            raise ValidationFailed(
                details=[
                    {
                        "field": "destination_amount",
                        "message": "Source and destination amounts must match.",
                    }
                ]
            )

        transfer = Transfer(
            source_account_id=source.id,
            destination_account_id=destination.id,
            source_amount=source_amount,
            destination_amount=destination_amount,
            source_currency=source.currency,
            destination_currency=destination.currency,
            occurred_at=occurred_at,
            notes=notes,
            status=TransferStatus.COMPLETED,
            idempotency_key=idempotency_key,
            created_by=actor_id,
        )
        self.db.add(transfer)
        self.db.flush()

        outgoing = self._write(
            Posting(source, Operation.TRANSFER_OUT, source_amount, TransactionType.TRANSFER),
            actor_id=actor_id,
            occurred_at=occurred_at,
            transfer_id=transfer.id,
            description=notes or f"Transfer to {destination.name}",
        )
        self._write(
            Posting(
                destination, Operation.TRANSFER_IN, destination_amount, TransactionType.TRANSFER
            ),
            actor_id=actor_id,
            occurred_at=occurred_at,
            transfer_id=transfer.id,
            description=notes or f"Transfer from {source.name}",
        )

        if fee_amount is not None:
            # An expense on the source, not part of the movement: folding it in
            # would claim the destination received it.
            self._write(
                Posting(source, Operation.EXPENSE, fee_amount, TransactionType.EXPENSE),
                actor_id=actor_id,
                occurred_at=occurred_at,
                description=f"{notes or f'Transfer to {destination.name}'} — fee",
                category_id=fee_category_id,
                fee_for_transaction_id=outgoing.id,
            )
        return transfer

    def record_loan_principal(
        self,
        *,
        account: Account,
        amount: Decimal,
        outgoing: bool,
        occurred_at: datetime,
        actor_id: uuid.UUID,
        **fields,
    ) -> Transaction:
        """Move the principal portion of a loan payment.

        Settling a debt already carried creates no wealth, so principal posts as
        TRANSFER and stays out of income and expense analytics — the same reason
        a card payment is not spending twice. Interest and fees post separately,
        and those are real income or expense.
        """
        operation = Operation.TRANSFER_OUT if outgoing else Operation.TRANSFER_IN
        return self._write(
            Posting(account, operation, amount, TransactionType.TRANSFER),
            actor_id=actor_id,
            occurred_at=occurred_at,
            **fields,
        )

    def cancel_transfer(self, transfer: Transfer, *, actor_id: uuid.UUID) -> Transfer:
        """Cancel both sides as one operation.

        Never leaves one side active without the other.
        """
        if transfer.status is TransferStatus.CANCELLED:
            raise Conflict("Transfer is already cancelled.", code="TRANSFER_ALREADY_CANCELLED")

        from app.db.base import utcnow

        sides = self.db.scalars(
            select(Transaction).where(Transaction.transfer_id == transfer.id)
        ).all()
        for side in sides:
            side.status = TransactionStatus.CANCELLED

        # A surviving fee would charge for a movement the ledger no longer shows.
        fees = self.db.scalars(
            select(Transaction).where(
                Transaction.fee_for_transaction_id.in_([s.id for s in sides])
            )
        ).all()
        for fee in fees:
            fee.status = TransactionStatus.CANCELLED
        transfer.status = TransferStatus.CANCELLED
        transfer.cancelled_at = utcnow()
        self.db.flush()

        from app.services import audit

        # Two balances move at once, and the transfer row records no actor.
        audit.record(
            self.db,
            actor=None,
            event_type=audit.TRANSFER_CANCELLED,
            entity_type=audit.TRANSFER,
            entity_id=transfer.id,
            metadata={"actor_user_id": str(actor_id)},
        )
        return transfer

    def adjust_balance(
        self,
        *,
        account: Account,
        actual_balance: Decimal,
        occurred_at: datetime,
        actor_id: uuid.UUID,
        reason: str | None = None,
    ) -> Transaction | None:
        """Reconcile to an observed balance.

        The delta is on the account's own scale, so a positive delta is an
        INCREASE for assets and liabilities alike.
        """
        current = self.balance_of(account)
        delta = actual_balance - current
        if delta == 0:
            return None

        direction = Direction.INCREASE if delta > 0 else Direction.DECREASE
        txn = Transaction(
            account_id=account.id,
            transaction_type=TransactionType.ADJUSTMENT,
            amount=abs(delta),
            direction=direction,
            currency=account.currency,
            occurred_at=occurred_at,
            status=TransactionStatus.COMPLETED,
            description=reason or "Balance adjustment",
            created_by=actor_id,
        )
        self.db.add(txn)
        self.db.flush()
        return txn

    # -------------------------------------------------------------- balances

    def balance_of(self, account: Account, *, as_of: datetime | None = None) -> Decimal:
        """Derived from the ledger, never from a cached column:

            opening_balance + SUM(INCREASE) - SUM(DECREASE)

        One formula serves both natures, direction already carrying the
        account's own perspective.
        """
        stmt = select(Transaction.direction, Transaction.amount).where(
            Transaction.account_id == account.id,
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.deleted_at.is_(None),
        )
        if as_of is not None:
            stmt = stmt.where(Transaction.occurred_at <= as_of)

        balance = Decimal(account.opening_balance)
        for direction, amount in self.db.execute(stmt):
            balance += amount if direction is Direction.INCREASE else -amount
        return balance

    def net_worth_contribution(self, account: Account) -> Decimal:
        """Signed contribution to net worth: assets add, liabilities subtract."""
        balance = self.balance_of(account)
        if nature_for(account.account_type) is AccountNature.LIABILITY:
            return -balance
        return balance
