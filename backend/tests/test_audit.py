"""The audit trail.

The trail exists for a shared household: when an account changes hands or a
transfer is cancelled, there must be a record that survives the thing it
describes. Two properties matter more than any single event — the trail is
append-only, and it never becomes a second copy of the ledger.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.db.enums import FamilyRole, TransactionType, Visibility
from app.models.records import AuditEvent
from app.services import accounts as account_service
from app.services import audit
from app.services import families as family_service
from app.services import transactions as txn_service

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def _events(db, event_type=None):
    rows = db.query(AuditEvent).order_by(AuditEvent.created_at).all()
    return [e for e in rows if event_type is None or e.event_type == event_type]


# ------------------------------------------------------------- what is recorded


def test_creating_an_account_is_recorded(db, user):
    from app.db.enums import AccountType

    account = account_service.create_account(
        db,
        user=user,
        name="New Bank",
        account_type=AccountType.CHECKING,
        currency="RWF",
        opening_balance=Decimal("1000"),
        opening_balance_at=NOW,
    )
    db.commit()
    events = _events(db, audit.ACCOUNT_CREATED)
    assert [e.entity_id for e in events] == [account.id]
    assert events[0].actor_user_id == user.id


def test_sharing_and_unsharing_are_distinguishable(db, user, family, bank_account):
    """"It changed" is not enough — the household needs to know which way."""
    account_service.set_visibility(
        db, account=bank_account, user=user, visibility=Visibility.SHARED
    )
    account_service.set_visibility(
        db, account=bank_account, user=user, visibility=Visibility.PRIVATE
    )
    db.commit()
    kinds = [e.event_type for e in _events(db) if e.entity_id == bank_account.id]
    # The fixture's own creation event leads; the two changes follow it.
    assert kinds == [
        audit.ACCOUNT_CREATED,
        audit.ACCOUNT_SHARED,
        audit.ACCOUNT_MADE_PRIVATE,
    ]


def test_the_visibility_change_records_both_ends(db, user, family, bank_account):
    account_service.set_visibility(
        db, account=bank_account, user=user, visibility=Visibility.SHARED
    )
    db.commit()
    event = _events(db, audit.ACCOUNT_SHARED)[0]
    assert event.event_metadata == {"from": "PRIVATE", "to": "SHARED"}


def test_spending_on_a_shared_account_is_its_own_event(db, user, family, bank_account):
    """A private purchase and a household one are not the same record."""
    txn_service.create_transaction(
        db,
        user=user,
        account_id=bank_account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("5000"),
        occurred_at=NOW,
        description="Private lunch",
    )
    account_service.set_visibility(
        db, account=bank_account, user=user, visibility=Visibility.SHARED
    )
    txn_service.create_transaction(
        db,
        user=user,
        account_id=bank_account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("9000"),
        occurred_at=NOW,
        description="Household shopping",
    )
    db.commit()
    kinds = [e.event_type for e in _events(db) if e.entity_type == audit.TRANSACTION]
    assert kinds == [audit.TRANSACTION_CREATED, audit.SHARED_TRANSACTION_CREATED]


def test_deleting_a_transaction_leaves_a_record_behind(db, user, bank_account):
    """The row is tombstoned, so this is the only thing that still says it
    happened."""
    txn = txn_service.create_transaction(
        db,
        user=user,
        account_id=bank_account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("5000"),
        occurred_at=NOW,
    )
    db.commit()
    txn_service.delete_transaction(db, user=user, transaction_id=txn.id)
    db.commit()
    assert [e.entity_id for e in _events(db, audit.TRANSACTION_DELETED)] == [txn.id]


def test_cancelling_a_transfer_is_recorded(db, user, bank_account, savings_account):
    from app.services.posting import PostingService

    posting = PostingService(db)
    transfer = posting.transfer_funds(
        source=bank_account,
        destination=savings_account,
        source_amount=Decimal("25000"),
        destination_amount=Decimal("25000"),
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()
    posting.cancel_transfer(transfer, actor_id=user.id)
    db.commit()
    events = _events(db, audit.TRANSFER_CANCELLED)
    assert [e.entity_id for e in events] == [transfer.id]
    assert events[0].event_metadata == {"actor_user_id": str(user.id)}


def test_household_membership_changes_are_recorded(db, user, other_user):
    fam = family_service.create_family(db, user=user, name="Home", base_currency="RWF")
    db.commit()
    _, token = family_service.invite(
        db, user=user, family_id=fam.id, invitee_email=None, proposed_role=FamilyRole.ADULT
    )
    db.commit()
    family_service.accept_invitation(db, user=other_user, token=token)
    db.commit()
    family_service.remove_member(
        db, user=user, family_id=fam.id, member_user_id=other_user.id
    )
    db.commit()

    assert [e.event_type for e in _events(db) if e.entity_type == audit.FAMILY] == [
        audit.FAMILY_CREATED,
        audit.FAMILY_MEMBER_INVITED,
        audit.FAMILY_MEMBER_JOINED,
        audit.FAMILY_MEMBER_REMOVED,
    ]


def test_a_loan_payment_is_recorded(db, user, bank_account):
    from app.db.enums import Frequency, LoanDirection
    from app.services import loans as loan_service

    loan = loan_service.create_loan(
        db,
        user=user,
        name="Car Loan",
        direction=LoanDirection.PAYABLE,
        currency="RWF",
        original_principal=Decimal("500000"),
        opening_outstanding_principal=Decimal("500000"),
        start_date=date(2026, 1, 1),
        expected_payment_amount=Decimal("50000"),
        payment_frequency=Frequency.MONTHLY,
        next_payment_date=date(2026, 9, 1),
    )
    db.commit()
    loan_service.record_payment(
        db,
        user=user,
        loan=loan,
        account_id=bank_account.id,
        total_amount=Decimal("50000"),
        principal_amount=Decimal("50000"),
        payment_date=date(2026, 9, 1),
        occurred_at=NOW,
    )
    db.commit()
    assert [e.entity_id for e in _events(db, audit.LOAN_PAYMENT_RECORDED)] == [loan.id]


# --------------------------------------------------- what must never be recorded


@pytest.mark.parametrize(
    "bad",
    [
        {"amount": "50000.00"},
        {"description": "Private therapy session"},
        {"balance": "1200000"},
        {"email": "someone@example.com"},
        {"account_identifier": "**** 7325"},
    ],
)
def test_financial_detail_is_refused_in_metadata(db, user, bad):
    """A copy of the record here would be a second, unreconciled ledger — and
    read by a wider audience than the record itself."""
    with pytest.raises(ValueError):
        audit.record(
            db,
            actor=user,
            event_type=audit.TRANSACTION_CREATED,
            entity_type=audit.TRANSACTION,
            entity_id=uuid.uuid4(),
            metadata=bad,
        )


def test_no_recorded_event_carries_an_amount(db, user, family, bank_account):
    """The guard is one thing; every real call obeying it is another."""
    account_service.set_visibility(
        db, account=bank_account, user=user, visibility=Visibility.SHARED
    )
    txn_service.create_transaction(
        db,
        user=user,
        account_id=bank_account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("123456"),
        occurred_at=NOW,
        description="Something private",
    )
    db.commit()
    for event in _events(db):
        blob = str(event.event_metadata or {})
        assert "123456" not in blob
        assert "Something private" not in blob


# ------------------------------------------------------------------- reading it


def test_unsharing_stays_in_the_households_trail(db, user, family, bank_account):
    """Un-sharing clears the account's family, and an event recorded against
    the cleared value would drop out of the very view that needs it."""
    account_service.set_visibility(
        db, account=bank_account, user=user, visibility=Visibility.SHARED
    )
    account_service.set_visibility(
        db, account=bank_account, user=user, visibility=Visibility.PRIVATE
    )
    db.commit()
    kinds = [e.event_type for e in audit.for_family(db, family_id=family.id)]
    assert audit.ACCOUNT_MADE_PRIVATE in kinds


def test_a_households_trail_is_readable_in_order(db, user, family, bank_account):
    account_service.set_visibility(
        db, account=bank_account, user=user, visibility=Visibility.SHARED
    )
    db.commit()
    rows = audit.for_family(db, family_id=family.id)
    # Newest first: the recent change is the one being looked for.
    assert rows[0].event_type == audit.ACCOUNT_SHARED


def test_one_entitys_history_can_be_pulled_out(db, user, family, bank_account):
    for visibility in (Visibility.SHARED, Visibility.PRIVATE, Visibility.SHARED):
        account_service.set_visibility(
            db, account=bank_account, user=user, visibility=visibility
        )
    db.commit()
    rows = audit.for_entity(db, entity_type=audit.ACCOUNT, entity_id=bank_account.id)
    # Three visibility changes on top of the account's creation.
    assert len(rows) == 4
    assert rows[0].event_type == audit.ACCOUNT_SHARED


def test_a_private_account_leaves_no_trail_in_the_household(db, user, family, bank_account):
    """Nothing about a private account should surface in the family's view.

    The household's own events are there, of course — what must not be is
    anything to do with an account nobody else can see.
    """
    txn_service.create_transaction(
        db,
        user=user,
        account_id=bank_account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("5000"),
        occurred_at=NOW,
    )
    db.commit()
    rows = audit.for_family(db, family_id=family.id)
    # Household events are expected; anything touching the private account is
    # not.
    assert {e.entity_type for e in rows} == {audit.FAMILY}


def test_the_trail_outlives_its_actor(db, other_user):
    """A departed member must not take the record of their actions with them.

    The foreign key is ON DELETE SET NULL for exactly this reason: the event
    still happened even once there is nobody left to point at.
    """
    from app.models.user import User

    audit.record(
        db,
        actor=other_user,
        event_type=audit.FAMILY_MEMBER_LEFT,
        entity_type=audit.FAMILY,
        entity_id=uuid.uuid4(),
    )
    db.commit()
    before = len(_events(db))
    assert before == 1

    db.query(User).filter(User.id == other_user.id).delete()
    db.commit()
    remaining = _events(db)
    assert len(remaining) == before
    assert remaining[0].actor_user_id is None
