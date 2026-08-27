"""Private transfer redaction.

Tested at the serialization layer: the point is what leaves the API, not what
the database holds.

The scenario: money moves from a shared household account into one member's
private account. The other member may see that it happened and for how much.
They may not learn anything about the private account.
"""

from datetime import UTC, datetime
from decimal import Decimal

from app.db.enums import Visibility
from app.services import authz
from app.services.posting import PostingService
from app.services.transactions import serialize_transfer
from tests.conftest import make_account

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def _shared_to_private(db, owner, other):
    shared = make_account(db, owner, "Household", Visibility.SHARED, opening="500000")
    private = make_account(db, other, "Their Private", Visibility.PRIVATE, opening="0")
    transfer = PostingService(db).transfer_funds(
        source=shared,
        destination=private,
        source_amount=Decimal("200000"),
        destination_amount=Decimal("200000"),
        occurred_at=NOW,
        actor_id=other.id,
    )
    db.commit()
    return shared, private, transfer


def test_the_other_member_sees_the_movement(db, user, other_user, family):
    _, _, transfer = _shared_to_private(db, user, other_user)
    payload = serialize_transfer(db, transfer, authz.resolve(db, user))

    assert payload["amount"] == "200000.00"
    assert payload["source_account"]["name"] == "Household"


def test_the_private_side_is_redacted(db, user, other_user, family):
    _, private, transfer = _shared_to_private(db, user, other_user)
    payload = serialize_transfer(db, transfer, authz.resolve(db, user))
    destination = payload["destination_account"]

    assert destination["display_name"] == "Private account"
    assert destination["visibility"] == "PRIVATE"


def test_the_private_account_id_never_leaves_the_api(db, user, other_user, family):
    """The id is the thing that would let someone go looking."""
    _, private, transfer = _shared_to_private(db, user, other_user)
    payload = serialize_transfer(db, transfer, authz.resolve(db, user))

    assert "id" not in payload["destination_account"]
    assert str(private.id) not in str(payload)


def test_the_private_account_name_never_leaves_the_api(db, user, other_user, family):
    _, _, transfer = _shared_to_private(db, user, other_user)
    payload = serialize_transfer(db, transfer, authz.resolve(db, user))
    assert "Their Private" not in str(payload)


def test_no_balance_or_metadata_leaks(db, user, other_user, family):
    _, private, transfer = _shared_to_private(db, user, other_user)
    payload = serialize_transfer(db, transfer, authz.resolve(db, user))
    destination = payload["destination_account"]
    for leaked in ("balance", "account_type", "masked_identifier", "owner"):
        assert leaked not in destination


def test_the_owner_of_the_private_account_sees_it_in_full(db, user, other_user, family):
    """Redaction is per viewer, not a property of the transfer."""
    _, private, transfer = _shared_to_private(db, user, other_user)
    payload = serialize_transfer(db, transfer, authz.resolve(db, other_user))

    assert payload["destination_account"]["id"] == str(private.id)
    assert payload["destination_account"]["name"] == "Their Private"


def test_the_linkage_is_not_broken_to_achieve_this(db, user, other_user, family):
    """do not solve redaction by severing the transfer
    in the database. It stays one logical movement with two entries."""
    from sqlalchemy import select

    from app.models.finance import Transaction

    _, _, transfer = _shared_to_private(db, user, other_user)
    sides = db.scalars(select(Transaction).where(Transaction.transfer_id == transfer.id)).all()
    assert len(sides) == 2


def test_an_outsider_sees_neither_side(db, user, other_user, family, third_user):
    _, _, transfer = _shared_to_private(db, user, other_user)
    payload = serialize_transfer(db, transfer, authz.resolve(db, third_user))

    assert payload["source_account"]["display_name"] == "Private account"
    assert payload["destination_account"]["display_name"] == "Private account"
    assert "id" not in payload["source_account"]
