"""Card expiry dates and the notice they generate.

A card is unusable the day after it expires, and the failure is silent: a
recurring charge simply stops working. The point of this feature is that the
warning arrives before that happens, and arrives once.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.core.errors import ValidationFailed
from app.db.enums import NotificationType
from app.models.planning import Notification
from app.services import credit_cards


def _set_expiry(db, card, month: int, year: int):
    card.expiry_month = month
    card.expiry_year = year
    db.commit()
    return card


def _notifications(db, user):
    return (
        db.query(Notification)
        .filter(
            Notification.user_id == user.id,
            Notification.notification_type == NotificationType.CARD_EXPIRING,
        )
        .all()
    )


# ------------------------------------------------------------- the expiry date


def test_a_card_lasts_to_the_end_of_its_printed_month(db, credit_card):
    """08/28 means the whole of August, not the first of it."""
    _set_expiry(db, credit_card, 8, 2028)
    assert credit_cards.expiry_date(credit_card) == date(2028, 8, 31)


def test_february_expiry_lands_on_the_real_month_end(db, credit_card):
    _set_expiry(db, credit_card, 2, 2028)
    assert credit_cards.expiry_date(credit_card) == date(2028, 2, 29)


def test_a_card_without_an_expiry_has_no_date(db, credit_card):
    assert credit_cards.expiry_date(credit_card) is None
    assert credit_cards.expiry_state(credit_card, today=date(2026, 8, 25)) is None


@pytest.mark.parametrize(
    "today,expected",
    [
        (date(2026, 1, 1), "VALID"),
        # The window opens 60 days out: 1 July is 61 days before 31 August.
        (date(2026, 7, 1), "VALID"),
        (date(2026, 7, 2), "EXPIRING"),
        (date(2026, 8, 31), "EXPIRING"),
        (date(2026, 9, 1), "EXPIRED"),
    ],
)
def test_status_moves_through_valid_expiring_expired(db, credit_card, today, expected):
    _set_expiry(db, credit_card, 8, 2026)
    assert credit_cards.expiry_state(credit_card, today=today)["status"] == expected


def test_the_last_day_still_counts_as_usable(db, credit_card):
    _set_expiry(db, credit_card, 8, 2026)
    state = credit_cards.expiry_state(credit_card, today=date(2026, 8, 31))
    assert state["days_remaining"] == 0
    assert state["status"] != "EXPIRED"


# ------------------------------------------------------------------- the notice


def test_a_card_inside_the_window_is_announced(db, credit_card, user):
    _set_expiry(db, credit_card, 8, 2026)
    assert credit_cards.notify_expiring_cards(db, today=date(2026, 7, 15)) == 1
    db.commit()
    sent = _notifications(db, user)
    assert len(sent) == 1
    assert "expires in 47 days" in sent[0].title
    assert sent[0].related_entity_id == credit_card.id


def test_a_card_outside_the_window_is_left_alone(db, credit_card, user):
    _set_expiry(db, credit_card, 8, 2028)
    assert credit_cards.notify_expiring_cards(db, today=date(2026, 7, 15)) == 0
    db.commit()
    assert _notifications(db, user) == []


def test_the_task_runs_daily_but_notifies_once(db, credit_card, user):
    """The whole point of the window guard: no drip of identical notices."""
    _set_expiry(db, credit_card, 8, 2026)
    credit_cards.notify_expiring_cards(db, today=date(2026, 7, 15))
    db.commit()
    for day in range(16, 25):
        credit_cards.notify_expiring_cards(db, today=date(2026, 7, day))
        db.commit()
    assert len(_notifications(db, user)) == 1


def test_replacing_the_card_earns_a_fresh_notice(db, credit_card, user):
    """A new expiry date is a new event, not a repeat of the old one."""
    _set_expiry(db, credit_card, 8, 2026)
    credit_cards.notify_expiring_cards(db, today=date(2026, 7, 15))
    db.commit()

    _set_expiry(db, credit_card, 8, 2029)
    credit_cards.notify_expiring_cards(db, today=date(2029, 7, 15))
    db.commit()
    assert len(_notifications(db, user)) == 2


def test_an_already_expired_card_is_reported_as_expired(db, credit_card, user):
    _set_expiry(db, credit_card, 6, 2026)
    credit_cards.notify_expiring_cards(db, today=date(2026, 8, 25))
    db.commit()
    assert "has expired" in _notifications(db, user)[0].title


def test_an_archived_card_is_not_chased(db, credit_card, user):
    from app.db.enums import AccountStatus

    _set_expiry(db, credit_card, 8, 2026)
    credit_card.status = AccountStatus.ARCHIVED
    db.commit()
    assert credit_cards.notify_expiring_cards(db, today=date(2026, 7, 15)) == 0


def test_a_non_card_account_is_never_considered(db, bank_account, savings_account, user):
    """Only cards expire. Nothing here should touch a bank account."""
    assert credit_cards.expiring_cards(db, today=date(2026, 8, 25)) == []


def test_another_user_is_not_told_about_your_card(db, credit_card, other_user):
    _set_expiry(db, credit_card, 8, 2026)
    credit_cards.notify_expiring_cards(db, today=date(2026, 7, 15))
    db.commit()
    assert _notifications(db, other_user) == []


# --------------------------------------------------------------- prepaid cards


def test_a_prepaid_card_expires_the_same_way(db, prepaid_card):
    """The plastic expires whether or not there is credit behind it."""
    _set_expiry(db, prepaid_card, 8, 2026)
    state = credit_cards.expiry_state(prepaid_card, today=date(2026, 7, 15))
    assert state["expires_on"] == "2026-08-31"
    assert state["status"] == "EXPIRING"


def test_a_prepaid_card_is_announced_too(db, prepaid_card, user):
    _set_expiry(db, prepaid_card, 8, 2026)
    assert credit_cards.notify_expiring_cards(db, today=date(2026, 7, 15)) == 1
    db.commit()
    sent = _notifications(db, user)
    assert len(sent) == 1
    # A prepaid card holds money you stand to lose; a credit card holds charges
    # you need to move. The advice should not be the same.
    assert "Spend or move the balance" in sent[0].body


def test_an_expiry_may_be_set_on_a_prepaid_card(db, prepaid_card):
    credit_cards.apply_card_fields(prepaid_card, {"expiry_month": 8, "expiry_year": 2026})
    assert prepaid_card.expiry_month == 8


def test_credit_only_fields_are_still_refused_on_a_prepaid_card(db, prepaid_card):
    """A prepaid card has no credit limit to speak of."""
    with pytest.raises(ValidationFailed) as exc:
        credit_cards.apply_card_fields(prepaid_card, {"credit_limit": Decimal("100")})
    assert exc.value.code == "NOT_A_CREDIT_CARD"


def test_an_expiry_is_still_refused_on_a_bank_account(db, bank_account):
    with pytest.raises(ValidationFailed) as exc:
        credit_cards.apply_card_fields(bank_account, {"expiry_month": 8, "expiry_year": 2026})
    assert exc.value.code == "NOT_A_CARD"


def test_an_expiry_can_be_cleared(db, credit_card):
    """Recorded by mistake has to be undoable."""
    _set_expiry(db, credit_card, 8, 2026)
    credit_cards.apply_card_fields(credit_card, {"expiry_month": None, "expiry_year": None})
    assert credit_cards.expiry_date(credit_card) is None


def test_both_kinds_of_card_are_listed_together(db, credit_card, prepaid_card):
    _set_expiry(db, credit_card, 8, 2026)
    _set_expiry(db, prepaid_card, 7, 2026)
    found = credit_cards.expiring_cards(db, today=date(2026, 7, 15))
    # Oldest expiry first, so the most urgent leads.
    assert [c.name for c, _ in found] == ["Prepaid Visa", "BK Visa"]


# ------------------------------------------------------------------- surfacing


def test_the_card_payload_carries_the_resolved_date(db, credit_card):
    """The client should never have to work out a month end."""
    _set_expiry(db, credit_card, 8, 2026)
    payload = credit_cards.summary(db, credit_card, today=date(2026, 7, 15))
    assert payload["expiry"]["expires_on"] == "2026-08-31"
    assert payload["expiry"]["status"] == "EXPIRING"


def test_the_account_payload_carries_expiry_for_any_card(db, prepaid_card, user):
    """Prepaid cards have no credit-card block to hide an expiry inside."""
    from app.services.accounts import serialize_account

    _set_expiry(db, prepaid_card, 8, 2026)
    payload = serialize_account(db, prepaid_card, user)
    assert payload["credit_card"] is None
    assert payload["expiry"]["expires_on"] == "2026-08-31"


def test_an_expiring_card_stays_visible_as_an_insight(db, credit_card, user):
    """The notification fires once; the insight is the standing state."""
    from app.services import insights as insight_service

    _set_expiry(db, credit_card, datetime.now(UTC).month, datetime.now(UTC).year)
    found = [
        i
        for i in insight_service.generate(db, user=user, context="personal")
        if i["code"] == "card_expiring"
    ]
    assert len(found) == 1
    assert found[0]["tone"] in {"warning", "negative"}


def test_the_advice_matches_what_the_card_holds(db, credit_card, prepaid_card):
    """A prepaid card has money on it to lose, not charges to move."""
    _set_expiry(db, credit_card, 8, 2026)
    _set_expiry(db, prepaid_card, 8, 2026)
    today = date(2026, 7, 15)
    assert "recurring charges" in credit_cards.expiry_state(credit_card, today=today)["advice"]
    assert "balance" in credit_cards.expiry_state(prepaid_card, today=today)["advice"]


def test_the_advice_changes_once_it_is_too_late(db, prepaid_card):
    _set_expiry(db, prepaid_card, 6, 2026)
    advice = credit_cards.expiry_state(prepaid_card, today=date(2026, 8, 25))["advice"]
    assert "no longer be reachable" in advice
