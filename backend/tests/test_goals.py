"""Savings goals.

A goal keeps no tally: its progress is the sum of the transfers tagged against
it. Most of these tests are about that staying true — and about the gap the
write path cannot close, where money leaves a goal's account untagged.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.enums import AccountType, GoalStatus, NotificationType, TransactionType, Visibility
from app.models.planning import Notification
from app.services import goals as goal_service
from app.services import transactions as txn_service
from app.services.posting import PostingService
from tests.conftest import make_account

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
TODAY = NOW.date()


@pytest.fixture
def pot(db, user):
    return make_account(
        db, user, "Savings", Visibility.PRIVATE, opening="0", account_type=AccountType.SAVINGS
    )


@pytest.fixture
def wallet(db, user):
    return make_account(db, user, "Bank", Visibility.PRIVATE, opening="2000000")


def _goal(db, user, pot, target="500000", when=None, name="Laptop"):
    goal = goal_service.create_goal(
        db,
        user=user,
        name=name,
        account=pot,
        target_amount=Decimal(target),
        target_date=when,
    )
    db.commit()
    return goal


def _row(db, user, name="Laptop"):
    return next(g for g in goal_service.list_goals(db, user=user) if g["name"] == name)


# ------------------------------------------------------------------ progress


def test_a_contribution_is_a_real_transfer(db, user, pot, wallet):
    goal = _goal(db, user, pot)
    goal_service.contribute(
        db, user=user, goal=goal, source=wallet, amount=Decimal("120000"), occurred_at=NOW
    )
    db.commit()

    posting = PostingService(db)
    # Money moved, and net worth did not change: it is a transfer.
    assert posting.balance_of(pot) == Decimal("120000")
    assert posting.balance_of(wallet) == Decimal("1880000")
    assert _row(db, user)["saved"] == "120000.00"


def test_progress_is_summed_from_the_tagged_transfers(db, user, pot, wallet):
    goal = _goal(db, user, pot)
    for amount in ("50000", "30000", "20000"):
        goal_service.contribute(
            db, user=user, goal=goal, source=wallet, amount=Decimal(amount), occurred_at=NOW
        )
    db.commit()
    assert _row(db, user)["saved"] == "100000.00"


def test_an_untagged_transfer_into_the_account_is_not_progress(db, user, pot, wallet):
    """The account holds it, but no goal claims it."""
    _goal(db, user, pot)
    PostingService(db).transfer_funds(
        source=wallet,
        destination=pot,
        source_amount=Decimal("200000"),
        destination_amount=Decimal("200000"),
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()

    assert PostingService(db).balance_of(pot) == Decimal("200000")
    assert _row(db, user)["saved"] == "0.00"


def test_two_goals_share_one_account_without_mixing(db, user, pot, wallet):
    """The point of tagging: one account, two goals, told apart by the tag."""
    laptop = _goal(db, user, pot, target="500000", name="Laptop")
    trip = _goal(db, user, pot, target="800000", name="Trip")
    goal_service.contribute(
        db, user=user, goal=laptop, source=wallet, amount=Decimal("100000"), occurred_at=NOW
    )
    goal_service.contribute(
        db, user=user, goal=trip, source=wallet, amount=Decimal("250000"), occurred_at=NOW
    )
    db.commit()

    assert _row(db, user, "Laptop")["saved"] == "100000.00"
    assert _row(db, user, "Trip")["saved"] == "250000.00"
    assert PostingService(db).balance_of(pot) == Decimal("350000")


def test_money_taken_back_out_reduces_progress(db, user, pot, wallet):
    goal = _goal(db, user, pot)
    goal_service.contribute(
        db, user=user, goal=goal, source=wallet, amount=Decimal("200000"), occurred_at=NOW
    )
    db.commit()

    out = PostingService(db).transfer_funds(
        source=pot,
        destination=wallet,
        source_amount=Decimal("50000"),
        destination_amount=Decimal("50000"),
        occurred_at=NOW,
        actor_id=user.id,
    )
    out.goal_id = goal.id
    db.commit()

    assert _row(db, user)["saved"] == "150000.00"


def test_a_cancelled_contribution_stops_counting(db, user, pot, wallet):
    goal = _goal(db, user, pot)
    transfer = goal_service.contribute(
        db, user=user, goal=goal, source=wallet, amount=Decimal("100000"), occurred_at=NOW
    )
    db.commit()
    assert _row(db, user)["saved"] == "100000.00"

    PostingService(db).cancel_transfer(transfer, actor_id=user.id)
    db.commit()
    assert _row(db, user)["saved"] == "0.00"


# ---------------------------------------------------------------------- pace


def test_a_dated_goal_says_what_it_takes_each_month(db, user, pot):
    # August to December is four months; 400,000 outstanding is 100,000 each.
    _goal(db, user, pot, target="400000", when=date(2026, 12, 14))
    assert _row(db, user)["required_monthly"] == "100000.00"


def test_a_goal_with_no_date_says_nothing_about_pace(db, user, pot):
    """An emergency fund is a real goal. Inventing a deadline to have a number
    would be answering a question nobody asked."""
    _goal(db, user, pot, target="400000", when=None)
    row = _row(db, user)
    assert row["target_date"] is None
    assert row["required_monthly"] is None


# ----------------------------------------------------------------- achieving


def test_reaching_the_target_marks_it_achieved(db, user, pot, wallet):
    goal = _goal(db, user, pot, target="100000")
    goal_service.contribute(
        db, user=user, goal=goal, source=wallet, amount=Decimal("100000"), occurred_at=NOW
    )
    db.commit()

    assert goal.status is GoalStatus.ACHIEVED
    assert goal.achieved_at is not None
    # The money stays where it is; a goal is a plan, not a vault.
    assert PostingService(db).balance_of(pot) == Decimal("100000")


def test_achieving_raises_a_notification(db, user, pot, wallet):
    goal = _goal(db, user, pot, target="100000")
    goal_service.contribute(
        db, user=user, goal=goal, source=wallet, amount=Decimal("100000"), occurred_at=NOW
    )
    db.commit()

    from sqlalchemy import select

    kinds = list(db.scalars(select(Notification.notification_type)))
    assert NotificationType.GOAL_ACHIEVED in kinds


def test_taking_the_money_back_out_un_achieves_it(db, user, pot, wallet):
    """Saying it is still achieved would be a claim the ledger no longer
    supports."""
    goal = _goal(db, user, pot, target="100000")
    goal_service.contribute(
        db, user=user, goal=goal, source=wallet, amount=Decimal("100000"), occurred_at=NOW
    )
    db.commit()
    assert goal.status is GoalStatus.ACHIEVED

    out = PostingService(db).transfer_funds(
        source=pot,
        destination=wallet,
        source_amount=Decimal("40000"),
        destination_amount=Decimal("40000"),
        occurred_at=NOW,
        actor_id=user.id,
    )
    out.goal_id = goal.id
    db.flush()
    goal_service.refresh_status(db, goal)
    db.commit()

    assert goal.status is GoalStatus.ACTIVE
    assert goal.achieved_at is None


def test_an_achieved_goal_stays_until_it_is_archived(db, user, pot, wallet):
    goal = _goal(db, user, pot, target="100000")
    goal_service.contribute(
        db, user=user, goal=goal, source=wallet, amount=Decimal("100000"), occurred_at=NOW
    )
    db.commit()
    assert len(goal_service.list_goals(db, user=user)) == 1

    goal_service.archive_goal(db, goal)
    db.commit()
    assert goal_service.list_goals(db, user=user) == []


# ------------------------------------------------------------ reconciliation


def test_spending_the_goal_money_untagged_is_a_shortfall(db, user, pot, wallet):
    """The case the write path cannot prevent: the money is the user's to
    spend, and spending it untagged is a normal thing to do."""
    goal = _goal(db, user, pot, target="500000")
    goal_service.contribute(
        db, user=user, goal=goal, source=wallet, amount=Decimal("300000"), occurred_at=NOW
    )
    db.commit()
    assert goal_service.shortfalls(db) == []

    txn_service.create_transaction(
        db,
        user=user,
        account_id=pot.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("120000"),
        occurred_at=NOW,
    )
    db.commit()

    found = goal_service.shortfalls(db)
    assert len(found) == 1
    assert found[0]["claimed"] == Decimal("300000")
    assert found[0]["balance"] == Decimal("180000")
    assert found[0]["short_by"] == Decimal("120000")


def test_a_shortfall_notifies_once_not_every_day(db, user, pot, wallet):
    goal = _goal(db, user, pot, target="500000")
    goal_service.contribute(
        db, user=user, goal=goal, source=wallet, amount=Decimal("300000"), occurred_at=NOW
    )
    txn_service.create_transaction(
        db,
        user=user,
        account_id=pot.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("120000"),
        occurred_at=NOW,
    )
    db.commit()

    assert goal_service.notify_shortfalls(db) == 1
    db.commit()
    # The condition persists until the user acts; saying so daily is noise.
    assert goal_service.notify_shortfalls(db) == 0


def test_the_shortfall_is_measured_per_account_not_per_goal(db, user, pot, wallet):
    """Goals sharing an account share its balance, so only the total says
    whether it is short."""
    a = _goal(db, user, pot, target="500000", name="Laptop")
    b = _goal(db, user, pot, target="500000", name="Trip")
    for goal in (a, b):
        goal_service.contribute(
            db, user=user, goal=goal, source=wallet, amount=Decimal("100000"), occurred_at=NOW
        )
    txn_service.create_transaction(
        db,
        user=user,
        account_id=pot.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("50000"),
        occurred_at=NOW,
    )
    db.commit()

    found = goal_service.shortfalls(db)
    assert len(found) == 1
    assert found[0]["claimed"] == Decimal("200000")
    assert found[0]["short_by"] == Decimal("50000")


def test_a_healthy_account_raises_nothing(db, user, pot, wallet):
    goal = _goal(db, user, pot, target="500000")
    goal_service.contribute(
        db, user=user, goal=goal, source=wallet, amount=Decimal("100000"), occurred_at=NOW
    )
    db.commit()
    assert goal_service.notify_shortfalls(db) == 0


# ------------------------------------------------------------------ lifecycle


def test_a_goal_cannot_save_into_a_card(db, user):
    card = make_account(
        db, user, "Visa", Visibility.PRIVATE, opening="0", account_type=AccountType.CREDIT_CARD
    )
    with pytest.raises(ValidationFailed):
        goal_service.create_goal(
            db, user=user, name="No", account=card, target_amount=Decimal("1000")
        )


def test_a_goal_cannot_be_funded_from_its_own_account(db, user, pot):
    goal = _goal(db, user, pot)
    with pytest.raises(ValidationFailed):
        goal_service.contribute(
            db, user=user, goal=goal, source=pot, amount=Decimal("100"), occurred_at=NOW
        )


def test_a_target_must_be_more_than_zero(db, user, pot):
    with pytest.raises(ValidationFailed):
        goal_service.create_goal(
            db, user=user, name="No", account=pot, target_amount=Decimal("0")
        )


def test_someone_elses_goal_is_not_found(db, user, other_user, pot):
    goal = _goal(db, user, pot)
    with pytest.raises(NotFound):
        goal_service.get_goal(db, goal.id, other_user)


def test_goals_are_private_to_their_owner(db, user, other_user, pot):
    _goal(db, user, pot)
    assert goal_service.list_goals(db, user=other_user) == []


def test_an_archived_goal_takes_no_more_money(db, user, pot, wallet):
    goal = _goal(db, user, pot)
    goal_service.archive_goal(db, goal)
    db.commit()
    with pytest.raises(Conflict):
        goal_service.contribute(
            db, user=user, goal=goal, source=wallet, amount=Decimal("100"), occurred_at=NOW
        )


def test_the_date_can_be_removed_once_set(db, user, pot):
    goal = _goal(db, user, pot, when=date(2026, 12, 1))
    goal_service.update_goal(db, goal=goal, clear_target_date=True)
    db.commit()
    assert _row(db, user)["target_date"] is None
