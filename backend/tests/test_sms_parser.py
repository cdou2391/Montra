"""Reading a mobile-money SMS into a draft.

The parser saves typing; it does not decide anything. So the tests care about
two things above all: that a real message yields the right numbers, and that
an unreadable one yields nothing rather than a guess. A blank field is obvious
on the form; an invented amount looks exactly like a real one.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from app.services.sms_parser import parse, resolve_accounts, serialize

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


# ------------------------------------------------------- your own accounts


TO_BANK = (
    "*165*S*50000 RWF transferred to your bank account at 2026-08-25 16:00:00. "
    "Fee: 500RWF. Balance: 2607RWF."
)


def test_moving_money_to_your_own_account_reads_as_a_transfer():
    """The difference from an expense is the word "your" — money that left the
    wallet but not the household."""
    result = parse(TO_BANK)
    assert result.transaction_type == "TRANSFER"
    assert result.amount == Decimal("50000")
    assert result.fee_amount == Decimal("500")


@pytest.mark.parametrize(
    "message",
    [
        "You have transferred 75000 RWF to your MTN Mobile Money account at 2026-08-25 16:05:00.",
        "Funds transfer of 120000 RWF from A/C ****1234 to A/C ****5678 on 2026-08-25 16:10.",
        "30000 RWF has been deposited to your bank account from your MoMo wallet at "
        "2026-08-25 16:20:00.",
    ],
)
def test_other_own_account_wordings(message):
    assert parse(message).transaction_type == "TRANSFER"


def test_a_transfer_claims_no_counterparty():
    """There is no other party — both ends are yours — so the field stays
    empty rather than being filled with "your bank account"."""
    assert parse(TO_BANK).counterparty is None


def test_paying_a_person_is_still_an_expense():
    """A transfer is only claimed when the message plainly says own-account.
    Money to a named person is spending, whoever they are."""
    assert parse(SENT).transaction_type == "EXPENSE"


def test_receiving_from_a_person_is_still_income():
    assert parse(RECEIVED).transaction_type == "INCOME"


def test_the_word_your_is_what_decides_it():
    """Same sentence, one word apart."""
    mine = "50000 RWF transferred to your bank account at 2026-08-25 16:00:00."
    theirs = "50000 RWF transferred to JEAN BOSCO at 2026-08-25 16:00:00."
    assert parse(mine).transaction_type == "TRANSFER"
    assert parse(theirs).transaction_type == "EXPENSE"


# ------------------------------------------------------ which account it is about


def test_a_momo_message_names_the_wallet():
    assert parse(SENT).channel == "MOBILE_MONEY"
    assert parse(RECEIVED).channel == "MOBILE_MONEY"


def test_a_momo_transfer_to_a_bank_is_still_a_momo_message():
    """The wallet is what moved and the wallet's balance is what it quotes.
    Reading this as a bank message would select the wrong account every time
    someone moves money out."""
    assert parse(TO_BANK).channel == "MOBILE_MONEY"


def test_a_bank_statement_names_the_bank():
    message = "Funds transfer of 120000 RWF from A/C ****1234 to A/C ****5678 on 2026-08-25 16:10."
    assert parse(message).channel == "BANK"


@pytest.mark.parametrize(
    "marker",
    ["*165*S*", "MTN Mobile Money", "your MoMo wallet", "Airtel Money", "FT Id: 123"],
)
def test_the_usual_momo_markers_are_recognised(marker):
    message = f"{marker} 1000 RWF transferred to JEAN at 2026-08-01 09:00:00."
    assert parse(message).channel == "MOBILE_MONEY"


def test_a_message_with_no_marker_claims_no_account():
    """Silence is better than picking an account the message never mentioned."""
    assert parse("You have sent 5000 RWF to JEAN at 2026-08-01 09:00:00.").channel is None


def test_the_channel_is_reported_in_the_payload():
    assert serialize(parse(SENT))["channel"] == "MOBILE_MONEY"
    assert "account" in serialize(parse(SENT))["matched"]


# --------------------------------------------------- a bank statement message


BK_TRANSFER = (
    "TRANSFER - EKASH Beneficiary: Cedric RUGAMBA Credited account: 0788863783 "
    "Debited account: 100020806359 Amount:RWF 250000.00 Transaction Charge:RWF 20 "
    "Event #:FTCM26237HCMRZABI Status: COMPLETED Date: 2026-08-25 15:28:02.307 "
    "Channel:MOBILE Available Balance:RWF 1,473,432 For enquiry call BK:250788143000/4455"
)


def test_a_labelled_statement_is_read_field_by_field():
    result = parse(BK_TRANSFER)
    assert result.amount == Decimal("250000.00")
    assert result.currency == "RWF"
    assert result.counterparty == "Cedric RUGAMBA"


def test_the_currency_may_sit_in_front_of_the_number():
    """RWF 250000.00, not 250000.00 RWF."""
    assert parse(BK_TRANSFER).amount == Decimal("250000.00")


def test_a_transaction_charge_is_a_fee_by_another_name():
    assert parse(BK_TRANSFER).fee_amount == Decimal("20")


def test_an_available_balance_is_a_balance_by_another_name():
    assert parse(BK_TRANSFER).balance_after == Decimal("1473432")


def test_milliseconds_are_dropped_not_choked_on():
    """The ledger records to the second; the message offers more."""
    assert parse(BK_TRANSFER).occurred_at == datetime(2026, 8, 25, 15, 28, 2)


def test_an_event_number_is_a_reference():
    assert parse(BK_TRANSFER).reference == "FTCM26237HCMRZABI"


def test_both_account_numbers_are_kept():
    result = parse(BK_TRANSFER)
    assert result.debited_identifier == "100020806359"
    assert result.credited_identifier == "0788863783"


# ------------------------------------------------------------- matching them


class FakeAccount:
    def __init__(self, name, identifier):
        self.id = name
        self.name = name
        self.account_identifier = identifier


def _accounts(*pairs):
    return [FakeAccount(name, ident) for name, ident in pairs]


def test_both_ends_ours_makes_it_a_transfer():
    """What the bank calls a transfer and what this ledger calls one are
    different questions; only the account list answers the second."""
    accounts = _accounts(("BK Current", "100020806359"), ("MTN MoMo", "0788863783"))
    resolved = resolve_accounts(parse(BK_TRANSFER), accounts)
    assert resolved["transaction_type"] == "TRANSFER"
    assert resolved["source_account_id"] == "BK Current"
    assert resolved["destination_account_id"] == "MTN MoMo"


def test_only_the_debited_end_ours_is_spending():
    """Money that left one of your accounts for somebody else's."""
    accounts = _accounts(("BK Current", "100020806359"))
    resolved = resolve_accounts(parse(BK_TRANSFER), accounts)
    assert resolved["transaction_type"] == "EXPENSE"
    assert resolved["source_account_id"] == "BK Current"
    assert resolved["destination_account_id"] is None


def test_only_the_credited_end_ours_is_income():
    accounts = _accounts(("MTN MoMo", "0788863783"))
    resolved = resolve_accounts(parse(BK_TRANSFER), accounts)
    assert resolved["transaction_type"] == "INCOME"
    assert resolved["destination_account_id"] == "MTN MoMo"


def test_neither_end_ours_selects_nothing():
    resolved = resolve_accounts(parse(BK_TRANSFER), _accounts(("Other", "999999")))
    assert resolved["source_account_id"] is None
    assert resolved["destination_account_id"] is None


def test_a_masked_number_still_matches_on_its_tail():
    """A message and a stored identifier rarely agree on masking."""
    accounts = _accounts(("BK Current", "**** 6359"), ("MTN MoMo", "0788863783"))
    resolved = resolve_accounts(parse(BK_TRANSFER), accounts)
    assert resolved["source_account_id"] == "BK Current"


def test_two_accounts_sharing_a_tail_match_neither():
    """Selecting the wrong account is worse than selecting none."""
    accounts = _accounts(("One", "111116359"), ("Two", "222226359"))
    resolved = resolve_accounts(parse(BK_TRANSFER), accounts)
    assert resolved["source_account_id"] is None


def test_too_few_digits_to_be_sure_matches_nothing():
    accounts = _accounts(("Short", "59"))
    assert resolve_accounts(parse(BK_TRANSFER), accounts)["source_account_id"] is None


def test_an_account_with_no_identifier_is_never_matched():
    accounts = _accounts(("Unnumbered", None))
    assert resolve_accounts(parse(BK_TRANSFER), accounts)["source_account_id"] is None


def test_the_earlier_momo_formats_still_resolve_nothing():
    """They carry no account numbers, so the channel remains the only hint."""
    resolved = resolve_accounts(parse(SENT), _accounts(("BK Current", "100020806359")))
    assert resolved["transaction_type"] == "EXPENSE"
    assert resolved["source_account_id"] is None


# ------------------------------------------------------- a merchant payment


MERCHANT = (
    "TxId:30121045018*S*Your payment of 20,000 RWF to AFRICA BUSINESS SERVICES "
    "Limit 999577 was completed at 2026-08-26 08:16:13.  Balance: 32,607 RWF. "
    "Fee 0 RWF.*EN#"
)


def test_a_merchant_payment_is_an_expense():
    result = parse(MERCHANT)
    assert result.understood is True
    assert result.transaction_type == "EXPENSE"
    assert result.amount == Decimal("20000")


def test_a_till_code_inside_the_sentence_does_not_defeat_the_name():
    """The code sits between the merchant and the verb, so the name has to be
    allowed to end at a digit. Without that the whole message parsed as
    nothing — no type, no amount, not just a missing name."""
    assert parse(MERCHANT).counterparty == "AFRICA BUSINESS SERVICES Limit"


def test_the_till_code_is_kept_separately():
    """Useful on its own: the same code identifies the same merchant next
    time, whatever the name is spelled like."""
    assert parse(MERCHANT).merchant_code == "999577"


def test_a_zero_fee_is_no_fee():
    """"Fee 0 RWF" must not post a zero line into the ledger."""
    assert parse(MERCHANT).fee_amount is None


def test_txid_without_a_space_is_a_reference():
    assert parse(MERCHANT).reference == "30121045018"


def test_the_networks_own_bookends_identify_it_as_momo():
    """This format carries no USSD prefix; *S* and *EN# are what mark it."""
    assert parse(MERCHANT).channel == "MOBILE_MONEY"


def test_the_balance_survives_the_thousands_separator():
    assert parse(MERCHANT).balance_after == Decimal("32607")


def test_the_moment_is_read_to_the_second():
    assert parse(MERCHANT).occurred_at == datetime(2026, 8, 26, 8, 16, 13)


# The digit terminator changed how every name ends, so the older formats are
# re-checked here rather than trusted.


def test_a_bracketed_phone_number_still_ends_a_name():
    assert parse(SENT).counterparty == "Denise NYIRAMUNINI"


def test_a_masked_number_still_ends_a_name():
    assert parse(RECEIVED).counterparty == "CEDRIC RUGAMBA"


def test_a_name_followed_by_at_still_ends_there():
    result = parse("You have sent 5000 RWF to JEAN BOSCO at 2026-08-01 09:00:00.")
    assert result.counterparty == "JEAN BOSCO"


def test_a_message_with_no_merchant_code_claims_none():
    assert parse(SENT).merchant_code is None
    assert parse(RECEIVED).merchant_code is None


def test_a_field_is_only_claimed_when_it_was_actually_filled():
    """"Fee 0 RWF" matches the pattern and yields nothing usable. Reporting it
    as filled would have the screen tell the user something untrue."""
    result = parse(MERCHANT)
    assert result.fee_amount is None
    assert "fee" not in result.matched
    # The balance did produce a value, so it is claimed.
    assert "balance" in result.matched


# ----------------------------------------------------------- a bill payment


BILL = (
    "Bill payment - Cash Power Electricity Credited account: 01026311843 "
    "Debited account: 100020806359 Amount: RWF 100,000 Transaction Charge: RWF 0 "
    "Event #: FTCM26238OT9NI371 Status: COMPLETED Date: 8/26/26, 11:10 AM  "
    "Channel:MOBILE  Voucher#: TK1:-1291-7440-1034-1082-4985 "
    "Available Balance: RWF 887,956 For enquiry call BK: 250788143000 / 4455"
)


def test_a_bill_payment_is_spending():
    """Both ends are named, but the credited one is a meter. Before this the
    message produced no type at all."""
    result = parse(BILL)
    assert result.understood is True
    assert result.transaction_type == "EXPENSE"
    assert result.amount == Decimal("100000")


def test_the_bill_names_what_was_bought():
    assert parse(BILL).counterparty == "Cash Power Electricity"


def test_the_electricity_token_is_kept():
    """It is what gets typed into the meter, and it exists nowhere else once
    the message is gone."""
    assert parse(BILL).voucher == "TK1:-1291-7440-1034-1082-4985"


def test_a_slash_date_with_a_meridiem_is_read():
    """8/26/26, 11:10 AM — the other shape this bank writes."""
    assert parse(BILL).occurred_at == datetime(2026, 8, 26, 11, 10)


@pytest.mark.parametrize(
    "written,expected",
    [
        ("1/2/26, 12:05 AM", datetime(2026, 1, 2, 0, 5)),
        ("1/2/26, 12:05 PM", datetime(2026, 1, 2, 12, 5)),
        ("12/31/26, 11:59 PM", datetime(2026, 12, 31, 23, 59)),
        ("3/4/2026, 09:07", datetime(2026, 3, 4, 9, 7)),
    ],
)
def test_midnight_and_noon_do_not_collide(written, expected):
    """12 AM is the start of the day and 12 PM the middle; the naive
    conversion gets both wrong."""
    assert parse(f"Bill payment - Water Debited account: 100020806359 "
                 f"Amount: RWF 500 Date: {written}").occurred_at == expected


def test_an_impossible_date_is_left_empty_rather_than_guessed():
    result = parse(
        "Bill payment - Water Debited account: 100020806359 Amount: RWF 500 "
        "Date: 13/45/26, 11:10 AM"
    )
    assert result.occurred_at is None


def test_a_zero_charge_on_a_bill_is_no_fee():
    assert parse(BILL).fee_amount is None


def test_the_bill_keeps_both_account_numbers():
    result = parse(BILL)
    assert result.debited_identifier == "100020806359"
    assert result.credited_identifier == "01026311843"


def test_paying_a_meter_is_not_a_transfer(): 
    """The credited account belongs to the utility, so only one end resolves
    and it stays spending."""
    accounts = [FakeAccount("BK Salary", "100020806359"), FakeAccount("MoMo", "0788863783")]
    resolved = resolve_accounts(parse(BILL), accounts)
    assert resolved["transaction_type"] == "EXPENSE"
    assert resolved["source_account_id"] == "BK Salary"
    assert resolved["destination_account_id"] is None


def test_the_declared_transfer_still_outranks_the_default():
    """The type default changed for labelled messages; the transfer case must
    not have been swept up in it."""
    accounts = [FakeAccount("BK Salary", "100020806359"), FakeAccount("MoMo", "0788863783")]
    assert resolve_accounts(parse(BK_TRANSFER), accounts)["transaction_type"] == "TRANSFER"


def test_a_message_without_a_voucher_claims_none():
    assert parse(BK_TRANSFER).voucher is None
    assert parse(SENT).voucher is None


def test_a_labelled_message_reports_the_amount_it_filled():
    """The prose patterns are skipped once the labelled reader has an amount,
    and they were the only thing reporting one."""
    assert "amount" in parse(BILL).matched
    assert "amount" in parse(BK_TRANSFER).matched


# ------------------------------------------------------------ a direct debit


DIRECT_DEBIT = (
    "*164*S*Y'ello, A transaction of 14000 RWF by DIRECT PAYMENT LTD  was completed "
    "at 2026-08-26 20:00:10. Balance:109507 RWF. Fee  0 RWF. FT Id: 30138330592. "
    "ET  Id: 64752860.*EN#"
)


def test_a_direct_debit_is_spending():
    """Worded from the merchant's side — "by" rather than "to" — but the money
    still leaves, and the balance it quotes is lower for it."""
    result = parse(DIRECT_DEBIT)
    assert result.understood is True
    assert result.transaction_type == "EXPENSE"
    assert result.amount == Decimal("14000")


def test_the_merchant_is_read_from_a_by_clause():
    assert parse(DIRECT_DEBIT).counterparty == "DIRECT PAYMENT LTD"


def test_a_name_ends_before_was_completed():
    """Nothing separates this name from the verb — no bracket, no digits, no
    full stop — so "was" has to end it or the name swallows the sentence."""
    assert "completed" not in (parse(DIRECT_DEBIT).counterparty or "")


def test_the_greeting_and_the_bookends_are_not_read_as_data():
    """The message opens with "Y'ello," and closes with *EN#."""
    result = parse(DIRECT_DEBIT)
    assert result.amount == Decimal("14000")
    assert result.channel == "MOBILE_MONEY"


def test_a_doubled_space_before_a_zero_fee_still_reads_as_no_fee():
    assert parse(DIRECT_DEBIT).fee_amount is None
    assert "fee" not in parse(DIRECT_DEBIT).matched


def test_the_direct_debit_keeps_its_reference_and_balance():
    result = parse(DIRECT_DEBIT)
    assert result.reference == "30138330592"
    assert result.balance_after == Decimal("109507")
    assert result.occurred_at == datetime(2026, 8, 26, 20, 0, 10)


# "was" now ends a name, so the formats that came before are re-asserted.


@pytest.mark.parametrize(
    "message,expected",
    [
        (SENT, "Denise NYIRAMUNINI"),
        (RECEIVED, "CEDRIC RUGAMBA"),
        (MERCHANT, "AFRICA BUSINESS SERVICES Limit"),
        (BILL, "Cash Power Electricity"),
    ],
)
def test_the_earlier_formats_still_name_the_same_party(message, expected):
    assert parse(message).counterparty == expected
