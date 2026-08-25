"""Reading a mobile-money SMS into a draft.

The parser saves typing; it does not decide anything. So the tests care about
two things above all: that a real message yields the right numbers, and that
an unreadable one yields nothing rather than a guess. A blank field is obvious
on the form; an invented amount looks exactly like a real one.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from app.services.sms_parser import parse, serialize

SENT = (
    "*165*S*200000 RWF transferred to Denise NYIRAMUNINI (250788308765) "
    "at 2026-08-25 15:28:59 .Fee: 1500RWF.Balance: 52607RWF."
    "Dial *182*1*3# and send money abroad *EN#"
)

RECEIVED = (
    "You have received 250000 RWF from CEDRIC RUGAMBA (*********915) "
    "at 2026-08-25 15:28:11. Message from sender: . Balance:254107 RWF. "
    "FT Id: 30107589757."
)


# ------------------------------------------------------------- money sent out


def test_sending_money_reads_as_an_expense(): 
    result = parse(SENT)
    assert result.transaction_type == "EXPENSE"
    assert result.amount == Decimal("200000")
    assert result.currency == "RWF"


def test_the_fee_is_read_separately_from_the_amount():
    """It is its own line in the ledger, so folding it in would overstate what
    was actually sent."""
    result = parse(SENT)
    assert result.fee_amount == Decimal("1500")
    assert result.amount == Decimal("200000")


def test_the_recipient_becomes_the_description():
    assert parse(SENT).counterparty == "Denise NYIRAMUNINI"


def test_the_moment_is_taken_from_the_message_not_from_now():
    """Pasting yesterday's SMS should record yesterday."""
    assert parse(SENT).occurred_at == datetime(2026, 8, 25, 15, 28, 59)


def test_the_seconds_survive():
    """This app records time of day, and a message states it exactly."""
    assert serialize(parse(SENT))["occurred_at"] == "2026-08-25T15:28:59"


def test_the_balance_is_reported_for_checking_against():
    assert parse(SENT).balance_after == Decimal("52607")


def test_the_trailing_advert_is_not_mistaken_for_data():
    """The message ends with a promo containing digits and asterisks."""
    result = parse(SENT)
    assert result.amount == Decimal("200000")
    assert result.counterparty == "Denise NYIRAMUNINI"


# ---------------------------------------------------------- money coming in


def test_receiving_money_reads_as_income():
    result = parse(RECEIVED)
    assert result.transaction_type == "INCOME"
    assert result.amount == Decimal("250000")
    assert result.counterparty == "CEDRIC RUGAMBA"


def test_a_masked_number_does_not_break_the_name():
    assert parse(RECEIVED).counterparty == "CEDRIC RUGAMBA"


def test_the_transaction_id_is_kept_as_a_reference():
    assert parse(RECEIVED).reference == "30107589757"


def test_an_empty_sender_message_is_not_read_as_a_name():
    result = parse(RECEIVED)
    assert result.counterparty == "CEDRIC RUGAMBA"
    assert result.balance_after == Decimal("254107")


def test_a_receipt_has_no_fee():
    assert parse(RECEIVED).fee_amount is None


# ------------------------------------------------------------------ variants


@pytest.mark.parametrize(
    "message,expected",
    [
        ("You have sent 5,000 RWF to JEAN PAUL at 2026-08-01 09:00:00.", Decimal("5000")),
        ("Payment of 12,500.50 RWF to SIMBA SUPERMARKET at 2026-08-02 10:30.", Decimal("12500.50")),
        ("10000 RWF withdrawn at 2026-08-03 11:00:00. Fee: 600RWF.", Decimal("10000")),
    ],
)
def test_other_outgoing_wordings(message, expected):
    result = parse(message)
    assert result.transaction_type == "EXPENSE"
    assert result.amount == expected


def test_a_thousands_separator_is_not_read_as_a_decimal_point():
    """5,000 is five thousand, not five."""
    result = parse("You have sent 5,000 RWF to JEAN at 2026-08-01 09:00:00.")
    assert result.amount == Decimal("5000")


def test_a_deposit_reads_as_income():
    result = parse("40000 RWF has been deposited at 2026-08-04 08:00:00. Balance: 90000RWF.")
    assert result.transaction_type == "INCOME"
    assert result.amount == Decimal("40000")


# ------------------------------------------------------- what must not happen


def test_an_unrecognised_message_yields_nothing(): 
    """Better a blank form than a confident wrong one."""
    result = parse("Your bundle of 5GB expires tomorrow. Dial *345# to renew.")
    assert result.understood is False
    assert result.transaction_type is None
    assert result.amount is None


def test_empty_input_is_handled():
    assert parse("").understood is False
    assert parse("   ").understood is False


def test_a_message_with_a_time_but_no_amount_is_not_understood():
    result = parse("Dear customer, your statement for 2026-08-25 10:00:00 is ready.")
    assert result.understood is False


def test_nothing_is_invented_when_a_field_is_absent():
    """No fee in the message means no fee on the form."""
    result = parse("You have sent 5000 RWF to JEAN at 2026-08-01 09:00:00.")
    assert result.fee_amount is None
    assert result.balance_after is None
    assert result.reference is None


def test_the_parser_reports_what_it_recognised():
    """So the screen can say what it filled in rather than silently changing
    fields."""
    assert set(parse(SENT).matched) >= {"expense", "fee", "balance", "timestamp"}


def test_the_payload_shape_is_stable_for_an_unreadable_message():
    payload = serialize(parse("nonsense"))
    assert payload["understood"] is False
    assert payload["amount"] is None
    assert payload["occurred_at"] is None
