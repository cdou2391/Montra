"""Card expiry dates and the notice they generate.

A card is unusable the day after it expires, and the failure is silent: a
recurring charge simply stops working. The point of this feature is that the
warning arrives before that happens, and arrives once.
"""

from datetime import UTC, date, datetime

import pytest

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


# ------------------------------------------------------------------- surfacing


def test_the_card_payload_carries_the_resolved_date(db, credit_card):
    """The client should never have to work out a month end."""
    _set_expiry(db, credit_card, 8, 2026)
    payload = credit_cards.summary(db, credit_card, today=date(2026, 7, 15))
    assert payload["expiry"]["expires_on"] == "2026-08-31"
    assert payload["expiry"]["status"] == "EXPIRING"


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
