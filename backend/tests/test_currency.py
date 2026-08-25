"""Converting balances into a reporting currency.

The bug this exists to prevent: a USD balance added to an RWF one as a raw
number. That does not give an approximate net worth, it gives a wrong one.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.core.errors import NotFound, ValidationFailed
from app.db.enums import AccountType
from app.services import accounts as account_service
from app.services import currency, reporting

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


@pytest.fixture
def usd_account(db, user):
    return account_service.create_account(
        db,
        user=user,
        name="BK Current USD",
        account_type=AccountType.CHECKING,
        currency="USD",
        opening_balance=Decimal("1000"),
        opening_balance_at=NOW,
    )


def _rate(db, user, base="USD", quote="RWF", value="1300"):
    return currency.set_rate(
        db,
        user=user,
        base_currency=base,
        quote_currency=quote,
        rate=Decimal(value),
        as_of=date(2026, 8, 25),
    )


# ------------------------------------------------------------- the conversion


def test_a_balance_is_converted_into_the_base_currency(db, user, usd_account):
    _rate(db, user)
    db.commit()
    converter = currency.converter_for(db, user=user)
    assert converter.convert(Decimal("1000"), "USD") == Decimal("1300000.0000")


def test_the_same_currency_converts_to_itself(db, user):
    converter = currency.converter_for(db, user=user)
    assert converter.convert(Decimal("500"), "RWF") == Decimal("500.0000")


def test_one_rate_defines_the_pair_both_ways(db, user):
    """Making the user enter the same fact twice invites them to contradict
    themselves."""
    _rate(db, user, base="USD", quote="RWF", value="1300")
    db.commit()
    converter = currency.converter_for(db, user=user)
    there = converter.rate("USD", "RWF")
    back = converter.rate("RWF", "USD")
    assert there == Decimal("1300")
    assert back == Decimal("0.00076923")


def test_an_unknown_currency_converts_to_nothing(db, user):
    """Not to the raw number — that is the bug."""
    converter = currency.converter_for(db, user=user)
    assert converter.convert(Decimal("1000"), "EUR") is None
    assert converter.can_convert("EUR") is False


# ----------------------------------------------------------------- net worth


def test_net_worth_converts_before_summing(db, user, bank_account, usd_account):
    _rate(db, user, value="1300")
    db.commit()
    position = reporting.net_worth(db, user=user)
    # 1,000,000 RWF + (1,000 USD x 1300) = 2,300,000
    assert position["assets"] == "2300000.00"
    assert position["unconverted_currencies"] == []


def test_an_unconvertible_balance_is_left_out_and_named(db, user, bank_account, usd_account):
    """Silently adding 1,000 dollars to a franc total would be worse than
    saying the dollars are not included."""
    db.commit()
    position = reporting.net_worth(db, user=user)
    assert position["assets"] == "1000000.00"
    assert position["unconverted_currencies"] == ["USD"]


def test_changing_the_rate_changes_the_total(db, user, usd_account):
    _rate(db, user, value="1300")
    db.commit()
    assert reporting.net_worth(db, user=user)["assets"] == "1300000.00"

    _rate(db, user, value="1400")
    db.commit()
    assert reporting.net_worth(db, user=user)["assets"] == "1400000.00"


def test_a_foreign_liability_is_converted_too(db, user):
    """A dollar card is dollars owed, and owing is not immune to arithmetic."""
    card = account_service.create_account(
        db,
        user=user,
        name="USD Card",
        account_type=AccountType.CREDIT_CARD,
        currency="USD",
        opening_balance=Decimal("200"),
        opening_balance_at=NOW,
    )
    assert card.currency == "USD"
    _rate(db, user, value="1300")
    db.commit()
    position = reporting.net_worth(db, user=user)
    assert position["liabilities"] == "260000.00"


# ------------------------------------------------------------- the payload


def test_the_account_payload_carries_the_converted_balance(db, user, usd_account):
    _rate(db, user, value="1300")
    db.commit()
    payload = account_service.serialize_account(db, usd_account, user)
    # The original is untouched: an account in dollars holds dollars.
    assert payload["balance"] == "1000.00"
    assert payload["currency"] == "USD"
    assert payload["balance_in_base"] == "1300000.00"
    assert payload["base_currency"] == "RWF"


def test_no_rate_means_no_converted_balance(db, user, usd_account):
    payload = account_service.serialize_account(db, usd_account, user)
    assert payload["balance"] == "1000.00"
    assert payload["balance_in_base"] is None


def test_a_base_currency_account_needs_no_rate(db, user, bank_account):
    payload = account_service.serialize_account(db, bank_account, user)
    assert payload["balance_in_base"] == payload["balance"]


# ------------------------------------------------------------- managing rates


def test_setting_the_same_pair_twice_updates_rather_than_duplicates(db, user):
    _rate(db, user, value="1300")
    _rate(db, user, value="1350")
    db.commit()
    rows = currency.list_rates(db, user=user)
    assert len(rows) == 1
    assert Decimal(rows[0].rate) == Decimal("1350")


def test_entering_the_pair_the_other_way_replaces_it(db, user):
    """The same fact stated in reverse is still one fact; two rows could
    disagree."""
    _rate(db, user, base="USD", quote="RWF", value="1300")
    db.commit()
    _rate(db, user, base="RWF", quote="USD", value="0.00077")
    db.commit()
    rows = currency.list_rates(db, user=user)
    assert len(rows) == 1
    assert (rows[0].base_currency, rows[0].quote_currency) == ("RWF", "USD")


def test_a_currency_cannot_be_worth_a_different_amount_of_itself(db, user):
    with pytest.raises(ValidationFailed) as exc:
        _rate(db, user, base="USD", quote="USD", value="2")
    assert exc.value.code == "SAME_CURRENCY"


@pytest.mark.parametrize("bad", ["0", "-5"])
def test_a_rate_must_be_positive(db, user, bad):
    with pytest.raises(ValidationFailed):
        _rate(db, user, value=bad)


@pytest.mark.parametrize("bad", ["US", "DOLLAR", "12X", ""])
def test_a_currency_code_is_three_letters(db, user, bad):
    with pytest.raises(ValidationFailed) as exc:
        _rate(db, user, base=bad)
    assert exc.value.code == "INVALID_CURRENCY"


def test_a_lowercase_code_is_accepted_and_stored_uppercase(db, user):
    rate = _rate(db, user, base="usd", quote="rwf", value="1300")
    assert (rate.base_currency, rate.quote_currency) == ("USD", "RWF")


def test_rates_are_per_user(db, user, other_user):
    _rate(db, user, value="1300")
    db.commit()
    assert currency.list_rates(db, user=other_user) == []
    assert currency.converter_for(db, user=other_user).can_convert("USD") is False


def test_another_users_rate_cannot_be_deleted(db, user, other_user):
    rate = _rate(db, user)
    db.commit()
    with pytest.raises(NotFound):
        currency.delete_rate(db, user=other_user, rate_id=rate.id)


def test_deleting_a_rate_stops_the_conversion(db, user, usd_account):
    rate = _rate(db, user, value="1300")
    db.commit()
    assert reporting.net_worth(db, user=user)["assets"] == "1300000.00"

    currency.delete_rate(db, user=user, rate_id=rate.id)
    db.commit()
    position = reporting.net_worth(db, user=user)
    assert position["assets"] == "0.00"
    assert position["unconverted_currencies"] == ["USD"]


# ------------------------------------------------------------- what needs one


def test_currencies_in_use_reports_what_is_actually_held(db, user, bank_account, usd_account):
    assert currency.currencies_in_use(db, user=user) == ["RWF", "USD"]
