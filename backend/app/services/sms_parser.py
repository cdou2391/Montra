"""Reading a mobile-money SMS into a draft transaction.

The point is to save typing, not to decide anything. Nothing here writes to
the ledger: it returns a draft the user reviews and submits, so a
misread message costs a correction rather than a wrong balance.

Every field is optional in the result. A parser that guesses to fill a gap is
worse than one that leaves it blank — a blank field is obvious on the form,
while an invented amount looks exactly like a real one.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

# Amounts arrive as 200000, 200,000 or 200000.50.
AMOUNT = r"([\d,]+(?:\.\d{1,2})?)"
CURRENCY = r"(RWF|USD|EUR|GBP|KES|UGX|TZS)"
# The same set without a capturing group, for the positions where the currency
# sits in front of the number and would otherwise shift every later index.
CURRENCY_NC = r"(?:RWF|USD|EUR|GBP|KES|UGX|TZS)"

# Milliseconds are matched so they are consumed rather than left dangling,
# but they are dropped: the ledger records to the second.
TIMESTAMP = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?")

# The other shape a bank writes: 8/26/26, 11:10 AM.
#
# Read as month/day/year, which is what this bank sends — 8/26/26 could be
# nothing else. A date where both halves are twelve or under is genuinely
# ambiguous and this will read it the same way; the form shows the date it
# chose, which is the only honest place to settle it.
TIMESTAMP_SLASH = re.compile(
    r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b,?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?",
    re.IGNORECASE,
)
# Banks and networks label the same thing differently, and some put the
# currency in front of the number rather than after it.
FEE = re.compile(
    rf"(?:fee|transaction\s+charge|charge)[:\s]*(?:{CURRENCY_NC}\s*)?{AMOUNT}\s*{CURRENCY}?",
    re.IGNORECASE,
)
# A card terminal separates thousands with a space and abbreviates the label:
# "Avail Bal RWF268 026". The digits are grouped in threes, so a space is only
# swallowed when three digits follow it — "Bal 5000 RWF" keeps its 5000.
# The grouped branch demands at least one separator, or it would match "254"
# out of "254107" and stop there — the alternation takes the first branch that
# succeeds, not the longest.
AMOUNT_GROUPED = r"(\d{1,3}(?:[ ,]\d{3})+(?:\.\d{1,2})?|[\d,]+(?:\.\d{1,2})?)"
# The leading currency is captured rather than skipped: a card alert quotes the
# purchase in one currency and the balance in another, and labelling the
# balance with the purchase's currency states something the message never said.
BALANCE = re.compile(
    rf"(?:new|available|avail\.?|current)?\s*\bbal(?:ance)?\b[:\s]*"
    rf"{CURRENCY}?\s*{AMOUNT_GROUPED}\s*{CURRENCY}?",
    re.IGNORECASE,
)
REFERENCE = re.compile(
    r"(?:financial\s+transaction\s+id|ft\s*id|transaction\s+id|txn?\s*id|event\s*#|"
    r"ref(?:erence)?)[:\s#]*([A-Za-z0-9]+)",
    re.IGNORECASE,
)

# A statement-style message: labelled fields rather than a sentence. The two
# account numbers are the useful part — they say which of the user's accounts
# each end is, which no amount of prose can.
DEBITED = re.compile(r"debited\s+account[:\s]*([\d*x]{4,})", re.IGNORECASE)
CREDITED = re.compile(r"credited\s+account[:\s]*([\d*x]{4,})", re.IGNORECASE)
LABELLED_AMOUNT = re.compile(
    rf"amount[:\s]*({CURRENCY_NC})?\s*{AMOUNT}\s*{CURRENCY}?", re.I
)
BENEFICIARY = re.compile(r"beneficiary[:\s]*([^\n:]{2,60}?)\s*(?:credited|debited|amount|$)", re.I)
DECLARED_TRANSFER = re.compile(r"^\s*transfer\b", re.IGNORECASE)

# "Bill payment - Cash Power Electricity". The header names what was bought,
# which is the only description the message offers.
BILL_SUBJECT = re.compile(
    r"bill\s+payment\s*[-–:]\s*([^\n]{2,60}?)\s*(?:credited|debited|amount|$)", re.I
)

# The token an electricity payment returns. Worth keeping above almost
# everything else in the message: it is what gets typed into the meter, and it
# exists nowhere else once the SMS is gone.
VOUCHER = re.compile(r"voucher\s*#?\s*:?\s*(\S{6,64})", re.IGNORECASE)

# A card authorisation alert, sent by the card network rather than the wallet:
#
#   RUGAMBA,USD10 Purchase approved with **4124 at Amsterdam on 01:35 26.08.26.
#   Avail Bal RWF268 026.
#
# The masked digits are the valuable part. They name the card outright, so the
# account is resolved from the number rather than guessed from the wording —
# which matters here because nothing else in the message says which card it is.
#
# Only an approved authorisation is read. A declined one moves no money, and a
# parser that prefilled it would put a purchase that never happened in front of
# someone who only has to press Add.
CARD_ALERT = re.compile(
    # Grouped, because the same terminal writes its balance as "RWF268 026" and
    # formats a purchase over 999 the same way.
    rf"\b({CURRENCY_NC})\s*{AMOUNT_GROUPED}\s+"
    # Whatever the terminal calls it: "Purchase", "Mail/phone Order", "ATM
    # Withdrawal". Listing the ones seen so far only works until the next one
    # arrives, so the anchor is "approved with <card>", which is the part that
    # makes this a card alert at all.
    r"([A-Za-z][A-Za-z/&.\- ]{0,40}?)\s+approved\s+"
    r"with\s+([*xX\d]{4,})",
    re.IGNORECASE,
)

# Money coming back rather than going out. The wording is the same up to the
# descriptor, and filing a refund as spending would be wrong twice over.
CARD_RETURNING = re.compile(r"refund|reversal|return|credit", re.IGNORECASE)

# Where it was spent, which is all the description this message offers. Ends at
# the time that follows, so "Amsterdam" does not run on into the date.
#
# Digits are allowed: a phone order names the merchant by its number, and
# "855-836-3987" is the only identification that message carries.
CARD_LOCATION = re.compile(r"\bat\s+([^\n]{2,60}?)\s+on\s+\d{1,2}:\d{2}", re.IGNORECASE)

# "01:35 26.08.26" — the time first, then a dotted date. Read day-first, which
# is what this sender writes and what the dots imply; the form shows the date
# it chose, which is the only honest place to settle an ambiguous one.
TIMESTAMP_DOTTED = re.compile(
    r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\s+(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b"
)

# A counterparty runs to the phone number, the timestamp, a full stop, or a
# run of digits — whichever comes first. Names carry spaces and mixed case, so
# the boundary has to be something other than whitespace.
#
# The digit terminator matters more than it looks: a merchant payment puts the
# till code inside the sentence ("to AFRICA BUSINESS SERVICES Limit 999577 was
# completed"), and without it the name has nowhere legal to end, so the whole
# pattern failed and the message parsed as nothing at all.
PARTY_TAIL = r"([^()\d.]{2,60}?)\s*(?:\(|\bat\b|\bwas\b|\d|\.|$)"

# The till or merchant code a payment quotes after the name.
MERCHANT_CODE = re.compile(
    r"\bto\s+[^()\d.]{2,60}?\s*(\d{4,12})\b(?=[^.]*?\bwas\s+completed\b|[^.]*?\bat\b)",
    re.IGNORECASE,
)

# Both orders occur in the wild: "200000 RWF transferred to X" and "You have
# sent 5,000 RWF to X". Amount-first is listed first so the more specific
# network wording wins when a message could arguably match either.
# Money moving between the user's own accounts. These are checked first,
# because "transferred to your bank account" would otherwise read as money
# leaving for someone else — the difference is the word "your".
#
# It only claims a transfer when the message says so plainly. A payment to a
# person who happens to be you is indistinguishable from a payment to anyone
# else, and guessing there would misfile real spending.
OWN_ACCOUNT = r"(?:your|my|own)\s+(?:\w+\s+){0,3}(?:account|wallet|momo|mobile\s+money|a/c)"

TRANSFERS = [
    re.compile(
        rf"{AMOUNT}\s*{CURRENCY}\s+(?:has been\s+)?(?:transferred|moved|sent)\s+(?:to|from)\s+"
        rf"{OWN_ACCOUNT}",
        re.I,
    ),
    re.compile(
        rf"(?:you have\s+)?(?:transferred|moved)\s+{AMOUNT}\s*{CURRENCY}\s+(?:to|from)\s+"
        rf"{OWN_ACCOUNT}",
        re.I,
    ),
    re.compile(
        rf"(?:funds\s+)?transfer\s+of\s+{AMOUNT}\s*{CURRENCY}\s+from\s+"
        rf"(?:a/c|account)[\s\w*]*\s+to\s+(?:a/c|account)",
        re.I,
    ),
    re.compile(
        rf"{AMOUNT}\s*{CURRENCY}\s+(?:has been\s+)?(?:deposited|credited)\s+(?:in)?to\s+"
        rf"{OWN_ACCOUNT}\s+from\s+{OWN_ACCOUNT}",
        re.I,
    ),
    re.compile(
        rf"(?:bank\s+to\s+wallet|wallet\s+to\s+bank)[^\d]{{0,40}}{AMOUNT}\s*{CURRENCY}",
        re.I,
    ),
]

OUTGOING = [
    re.compile(rf"{AMOUNT}\s*{CURRENCY}\s+(?:has been\s+)?transferred\s+to\s+{PARTY_TAIL}", re.I),
    re.compile(rf"{AMOUNT}\s*{CURRENCY}\s+(?:has been\s+)?sent\s+to\s+{PARTY_TAIL}", re.I),
    re.compile(
        rf"(?:you have\s+)?(?:sent|transferred)\s+{AMOUNT}\s*{CURRENCY}\s+to\s+{PARTY_TAIL}",
        re.I,
    ),
    re.compile(rf"(?:you have\s+)?paid\s+{AMOUNT}\s*{CURRENCY}\s+to\s+{PARTY_TAIL}", re.I),
    re.compile(rf"payment\s+of\s+{AMOUNT}\s*{CURRENCY}\s+to\s+{PARTY_TAIL}", re.I),
    # A direct debit, worded from the merchant's side: "a transaction of X by
    # NAME". "by" rather than "to", but the money still leaves — the balance
    # the message quotes is lower for it.
    re.compile(
        rf"transaction\s+of\s+{AMOUNT}\s*{CURRENCY}\s+(?:by|to|from)\s+{PARTY_TAIL}",
        re.I,
    ),
    re.compile(rf"{AMOUNT}\s*{CURRENCY}\s+withdrawn", re.I),
]

INCOMING = [
    re.compile(rf"you have received\s+{AMOUNT}\s*{CURRENCY}\s+from\s+{PARTY_TAIL}", re.I),
    re.compile(rf"{AMOUNT}\s*{CURRENCY}\s+received\s+from\s+{PARTY_TAIL}", re.I),
    re.compile(rf"received\s+{AMOUNT}\s*{CURRENCY}\s+from\s+{PARTY_TAIL}", re.I),
    re.compile(rf"{AMOUNT}\s*{CURRENCY}\s+(?:has been\s+)?deposited", re.I),
]


# Which kind of account the message is *about* — the one whose balance it
# reports. A MoMo message announcing a transfer to a bank is still a MoMo
# message: the wallet is what moved, and the wallet's balance is what it
# quotes.
MOMO_MARKERS = (
    re.compile(r"\*1(?:65|82|85)\*"),          # MTN and Airtel USSD codes
    # The same networks top and tail their messages with these even when the
    # USSD prefix is absent, which is how a merchant payment identifies itself.
    re.compile(r"\*S\*"),
    re.compile(r"\*EN#"),
    re.compile(r"mobile\s*money", re.I),
    re.compile(r"\bmomo\b", re.I),
    re.compile(r"airtel\s+money", re.I),
    re.compile(r"\bft\s*id\b", re.I),          # MTN MoMo transaction id
    re.compile(r"\byello\b", re.I),
)

BANK_MARKERS = (
    re.compile(r"\ba/c\b", re.I),
    re.compile(r"bank\s+of\s+kigali", re.I),
    re.compile(r"\bequity\b|\bcogebanque\b|\bi&m\b", re.I),
    re.compile(r"account\s+(?:number|no\.?)\s*[:\s]*\d", re.I),
    re.compile(r"(?:debited|credited)\s+account", re.I),
)


def _channel(text: str) -> str | None:
    """MOBILE_MONEY, BANK, or nothing.

    MoMo is checked first and wins outright. Its messages routinely mention a
    bank as the other end of a movement, and reading that as "this is a bank
    message" would select the wrong account every time someone tops up.
    """
    if any(marker.search(text) for marker in MOMO_MARKERS):
        return "MOBILE_MONEY"
    if any(marker.search(text) for marker in BANK_MARKERS):
        return "BANK"
    return None


@dataclass
class ParsedSms:
    transaction_type: str | None = None
    channel: str | None = None
    voucher: str | None = None
    # The till code a merchant payment quotes. Kept separate from the name so
    # it can be recognised later without re-reading the description.
    merchant_code: str | None = None
    # Raw account numbers as the message wrote them. Resolving these to the
    # user's accounts needs the stored identifiers, which only the API has.
    debited_identifier: str | None = None
    credited_identifier: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    fee_amount: Decimal | None = None
    occurred_at: datetime | None = None
    counterparty: str | None = None
    balance_after: Decimal | None = None
    # The balance's own currency, which need not be the purchase's.
    balance_currency: str | None = None
    reference: str | None = None
    matched: list[str] = field(default_factory=list)

    @property
    def understood(self) -> bool:
        """Enough to be worth prefilling: what kind, and how much."""
        return self.transaction_type is not None and self.amount is not None


def _decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        # Separators only: a number never contains meaningful whitespace, and
        # a card terminal groups thousands with a space rather than a comma.
        value = Decimal(re.sub(r"[,\s]", "", raw))
    except (InvalidOperation, AttributeError):
        return None
    return value if value > 0 else None


def _clean_party(raw: str | None) -> str | None:
    if not raw:
        return None
    # Strip the connective words a name sometimes trails.
    name = re.sub(r"\s+", " ", raw).strip(" .,-")
    name = re.sub(r"\s+(?:at|on|via)$", "", name, flags=re.IGNORECASE).strip()
    return name or None


def _read_slash_timestamp(text: str, result: ParsedSms) -> None:
    found = TIMESTAMP_SLASH.search(text)
    if not found:
        return
    month, day, year, hour, minute, second, meridiem = found.groups()
    year = int(year)
    if year < 100:
        year += 2000
    hour = int(hour)
    if meridiem:
        meridiem = meridiem.upper()
        if meridiem == "PM" and hour != 12:
            hour += 12
        elif meridiem == "AM" and hour == 12:
            hour = 0
    try:
        result.occurred_at = datetime(
            year, int(month), int(day), hour, int(minute), int(second or 0)
        )
    except ValueError:
        return
    result.matched.append("timestamp")


def _read_labelled(text: str, result: ParsedSms) -> None:
    """Read a statement-style message: Label: value, Label: value.

    Only fills what is actually labelled. The type is left for the caller to
    settle, because "TRANSFER" in a bank message means money moved — not that
    it moved between two accounts the *user* owns, which is a question only
    their account list can answer.
    """
    debited = DEBITED.search(text)
    credited = CREDITED.search(text)
    if not (debited or credited):
        return

    result.debited_identifier = debited.group(1) if debited else None
    result.credited_identifier = credited.group(1) if credited else None
    result.matched.append("accounts")

    amount = LABELLED_AMOUNT.search(text)
    if amount:
        # The currency may sit on either side of the number.
        result.currency = (amount.group(1) or amount.group(3) or "").upper() or None
        result.amount = _decimal(amount.group(2))
        if result.amount is not None:
            # The prose patterns are skipped once this has an amount, and they
            # were the only thing reporting one — so a labelled message filled
            # the field and then told the user it had not.
            result.matched.append("amount")

    party = BENEFICIARY.search(text)
    if party:
        result.counterparty = _clean_party(party.group(1))

    subject = BILL_SUBJECT.search(text)
    if subject and not result.counterparty:
        result.counterparty = _clean_party(subject.group(1))

    voucher = VOUCHER.search(text)
    if voucher:
        result.voucher = voucher.group(1)
        result.matched.append("voucher")

    if DECLARED_TRANSFER.search(text):
        # Provisional: refined once the identifiers are matched against real
        # accounts. A bank calls it a transfer whoever the beneficiary is.
        result.transaction_type = "TRANSFER"
        result.matched.append("transfer")
    elif credited and not debited:
        result.transaction_type = "INCOME"
    else:
        # Money left the debited account. A bill payment names both ends, but
        # the credited one is a meter or a till rather than anything of the
        # user's — resolve_accounts settles that against their real accounts.
        result.transaction_type = "EXPENSE"


def _read_card_alert(text: str, result: ParsedSms) -> None:
    """Read a card authorisation alert.

    The card is recorded as the debited account so it resolves the same way a
    statement's account number does — the caller matches it against the user's
    real accounts, and an unmatched card leaves the field blank rather than
    falling back to a default.
    """
    found = CARD_ALERT.search(text)
    if not found:
        return

    currency, amount, descriptor, card = found.groups()
    result.amount = _decimal(amount)
    if result.amount is None:
        return
    result.currency = currency.upper()
    returning = bool(CARD_RETURNING.search(descriptor))
    result.transaction_type = "INCOME" if returning else "EXPENSE"
    result.matched.append("income" if returning else "expense")

    # Which end the card is depends on which way the money went. Both resolve
    # the same way; naming the wrong one would still fill the form correctly
    # and still be a lie about what the message said.
    if returning:
        result.credited_identifier = card
    else:
        result.debited_identifier = card
    result.matched.append("accounts")

    where = CARD_LOCATION.search(text)
    if where:
        result.counterparty = _clean_party(where.group(1))


def _read_dotted_timestamp(text: str, result: ParsedSms) -> None:
    found = TIMESTAMP_DOTTED.search(text)
    if not found:
        return
    hour, minute, second, day, month, year = found.groups()
    year = int(year)
    if year < 100:
        year += 2000
    try:
        result.occurred_at = datetime(
            year, int(month), int(day), int(hour), int(minute), int(second or 0)
        )
    except ValueError:
        return
    result.matched.append("timestamp")


def parse(message: str) -> ParsedSms:
    """Read what the message plainly says, and nothing more."""
    result = ParsedSms()
    if not message or not message.strip():
        return result

    text = message.strip()

    # A labelled statement is unambiguous where prose is not, so it is read
    # first and the sentence patterns are skipped when it succeeds.
    _read_labelled(text, result)
    # A card alert is as unambiguous as a labelled statement — it names the
    # card outright — so it is read before the prose patterns too.
    if result.amount is None:
        _read_card_alert(text, result)

    result.channel = _channel(text)
    if result.channel:
        result.matched.append("account")

    for kind, patterns in (
        ("TRANSFER", TRANSFERS),
        ("EXPENSE", OUTGOING),
        ("INCOME", INCOMING),
    ):
        if result.amount is not None:
            break  # already read from labelled fields
        for pattern in patterns:
            found = pattern.search(text)
            if not found:
                continue
            groups = found.groups()
            result.transaction_type = kind
            result.amount = _decimal(groups[0])
            result.currency = (groups[1] or "").upper() or None
            if len(groups) > 2 and groups[2]:
                result.counterparty = _clean_party(groups[2])
            result.matched.append(kind.lower())
            break
        if result.transaction_type:
            break

    # The fee is its own line in the ledger, so it is read separately and never
    # folded into the amount above.
    fee = FEE.search(text)
    if fee:
        result.fee_amount = _decimal(fee.group(1))
        # Only claimed when a usable value came out. "Fee 0 RWF" matches the
        # pattern and yields nothing, and saying a field was filled when it
        # was left empty is a small lie the screen then repeats.
        if result.fee_amount is not None:
            result.matched.append("fee")

    balance = BALANCE.search(text)
    if balance:
        leading, amount, trailing = balance.groups()
        result.balance_after = _decimal(amount)
        if result.balance_after is not None:
            result.balance_currency = (leading or trailing or "").upper() or None
            result.matched.append("balance")

    stamp = TIMESTAMP.search(text)
    if stamp is None:
        _read_slash_timestamp(text, result)
        if result.occurred_at is None:
            _read_dotted_timestamp(text, result)
    if stamp:
        raw = f"{stamp.group(1)} {stamp.group(2)}"
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                # Naive on purpose: the message is in the sender's local time,
                # and the caller anchors it to the user's zone the same way a
                # typed date is anchored.
                result.occurred_at = datetime.strptime(raw, fmt)
                result.matched.append("timestamp")
                break
            except ValueError:
                continue

    code = MERCHANT_CODE.search(text)
    if code:
        result.merchant_code = code.group(1)
        result.matched.append("merchant")

    reference = REFERENCE.search(text)
    if reference:
        result.reference = reference.group(1)
        result.matched.append("reference")

    return result


def serialize(parsed: ParsedSms) -> dict:
    from app.core.money import serialize as serialize_amount

    return {
        "understood": parsed.understood,
        "transaction_type": parsed.transaction_type,
        # The client matches this to one of the user's accounts; it deliberately
        # names a kind rather than an account, because only the client knows
        # which accounts exist.
        "channel": parsed.channel,
        "merchant_code": parsed.merchant_code,
        "voucher": parsed.voucher,
        "debited_identifier": parsed.debited_identifier,
        "credited_identifier": parsed.credited_identifier,
        "amount": serialize_amount(parsed.amount) if parsed.amount is not None else None,
        "currency": parsed.currency,
        "fee_amount": (
            serialize_amount(parsed.fee_amount) if parsed.fee_amount is not None else None
        ),
        # Naive local time, seconds kept. The form displays to the minute but
        # holds this string, so the moment the message recorded survives
        # unless the user edits the field.
        "occurred_at": (
            parsed.occurred_at.strftime("%Y-%m-%dT%H:%M:%S") if parsed.occurred_at else None
        ),
        "counterparty": parsed.counterparty,
        "balance_after": (
            serialize_amount(parsed.balance_after) if parsed.balance_after is not None else None
        ),
        "balance_currency": parsed.balance_currency,
        "reference": parsed.reference,
        "matched": parsed.matched,
    }


# --------------------------------------------------------------- resolution

# Enough of an account number to be sure, without demanding the whole thing:
# a message may mask all but the tail, and the stored identifier may itself be
# only the last few characters.
MATCH_DIGITS = 4


def _digits(value: str | None) -> str:
    return "".join(c for c in (value or "") if c.isdigit())


def match_account(identifier: str | None, accounts) -> object | None:
    """The user's account this number refers to, if exactly one does.

    Compared on trailing digits, because a message and a stored identifier
    rarely agree on masking. Ambiguity returns nothing: selecting the wrong
    account is worse than selecting none, and the user is about to look at the
    form either way.
    """
    tail = _digits(identifier)
    if len(tail) < MATCH_DIGITS:
        return None
    tail = tail[-MATCH_DIGITS:]

    hits = [a for a in accounts if _digits(a.account_identifier).endswith(tail)]
    return hits[0] if len(hits) == 1 else None


def _currency_conversion(parsed: ParsedSms, account, converter) -> dict | None:
    """The message's amount restated in the account's own currency.

    A card denominated in francs still gets a dollar figure texted to it when
    the purchase was abroad, and a ledger entry is always in its account's
    currency — so filling the dollar figure straight into the form would record
    ten francs for a ten dollar purchase.

    This is a starting point and says so. The rate here is the daily market
    one; the bank's rate, plus whatever margin it takes, is on the statement
    and is the number that actually gets charged. Returning the pair rather
    than silently swapping the amount is what lets the form say as much.
    """
    if account is None or parsed.amount is None or not parsed.currency:
        return None
    target = (account.currency or "").upper()
    if not target or target == parsed.currency.upper():
        return None

    from app.core.money import serialize as serialize_amount

    converted = converter.convert(parsed.amount, parsed.currency, target) if converter else None
    rate = converter.rate(parsed.currency, target) if converter else None
    return {
        "from_currency": parsed.currency.upper(),
        "from_amount": serialize_amount(parsed.amount),
        "to_currency": target,
        # None when no rate is known. The mismatch is still worth reporting:
        # the amount on the form is in the wrong currency either way, and the
        # user is the one who can fix it.
        "amount": serialize_amount(converted) if converted is not None else None,
        "rate": str(rate) if rate is not None else None,
    }


def resolve_accounts(parsed: ParsedSms, accounts, converter=None) -> dict:
    """Turn the message's account numbers into the user's accounts.

    This is what settles the type. A bank calls it a transfer whoever the
    beneficiary is; it is a transfer *in this ledger* only when both ends are
    accounts the user holds. One end matching means money genuinely left or
    arrived, which is spending or income.
    """
    source = match_account(parsed.debited_identifier, accounts)
    destination = match_account(parsed.credited_identifier, accounts)

    kind = parsed.transaction_type
    if source is not None and destination is not None:
        kind = "TRANSFER"
    elif parsed.transaction_type == "TRANSFER":
        # Declared a transfer by the bank, but only one end is ours.
        kind = "EXPENSE" if source is not None else "INCOME" if destination is not None else kind

    return {
        "transaction_type": kind,
        "source_account_id": str(source.id) if source is not None else None,
        "destination_account_id": str(destination.id) if destination is not None else None,
        # Against the account the entry lands on, which is the one whose
        # currency the amount has to be in.
        "currency_conversion": _currency_conversion(
            parsed, source if source is not None else destination, converter
        ),
    }
