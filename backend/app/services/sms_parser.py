"""Reading a mobile-money, bank or card SMS into a draft transaction.

Writes nothing: the user reviews and submits, so a misread costs a correction
rather than a wrong balance. Every field is optional — a blank is obvious on
the form, while an invented amount looks exactly like a real one.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

# 200000, 200,000 or 200000.50.
AMOUNT = r"([\d,]+(?:\.\d{1,2})?)"
CURRENCY = r"(RWF|USD|EUR|GBP|KES|UGX|TZS)"
# Non-capturing, for currency-first positions that would otherwise shift every
# later group index.
CURRENCY_NC = r"(?:RWF|USD|EUR|GBP|KES|UGX|TZS)"

# Milliseconds are consumed but dropped; the ledger records to the second.
TIMESTAMP = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?")

# "8/26/26, 11:10 AM". Month-first, as this bank sends. Both halves under 12 is
# genuinely ambiguous; the form shows the date it chose.
TIMESTAMP_SLASH = re.compile(
    r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b,?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?",
    re.IGNORECASE,
)
# The currency sits on either side, depending on the sender.
FEE = re.compile(
    rf"(?:fee|transaction\s+charge|charge)[:\s]*(?:{CURRENCY_NC}\s*)?{AMOUNT}\s*{CURRENCY}?",
    re.IGNORECASE,
)
# A card terminal groups thousands with a space: "Avail Bal RWF268 026". The
# grouped branch must demand a separator, or it matches "254" out of "254107"
# and stops — alternation takes the first branch that succeeds, not the longest.
AMOUNT_GROUPED = r"(\d{1,3}(?:[ ,]\d{3})+(?:\.\d{1,2})?|[\d,]+(?:\.\d{1,2})?)"
# The leading currency is captured: a card alert quotes the purchase in one
# currency and the balance in another.
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

# A statement-style message: labelled fields rather than prose. The two account
# numbers say which of the user's accounts each end is.
DEBITED = re.compile(r"debited\s+account[:\s]*([\d*x]{4,})", re.IGNORECASE)
CREDITED = re.compile(r"credited\s+account[:\s]*([\d*x]{4,})", re.IGNORECASE)
LABELLED_AMOUNT = re.compile(
    rf"amount[:\s]*({CURRENCY_NC})?\s*{AMOUNT}\s*{CURRENCY}?", re.I
)
BENEFICIARY = re.compile(r"beneficiary[:\s]*([^\n:]{2,60}?)\s*(?:credited|debited|amount|$)", re.I)
DECLARED_TRANSFER = re.compile(r"^\s*transfer\b", re.IGNORECASE)

# "Bill payment - Cash Power Electricity" — the only description on offer.
BILL_SUBJECT = re.compile(
    r"bill\s+payment\s*[-–:]\s*([^\n]{2,60}?)\s*(?:credited|debited|amount|$)", re.I
)

# The meter token an electricity payment returns. It exists nowhere else once
# the SMS is gone.
VOUCHER = re.compile(r"voucher\s*#?\s*:?\s*(\S{6,64})", re.IGNORECASE)

# A card network alert:
#   RUGAMBA,USD10 Purchase approved with **4124 at Amsterdam on 01:35 26.08.26.
#
# Anchored on "approved with <card>" rather than on a list of words for what
# was bought, which only holds until the terminal uses a new one. Only approved
# authorisations: a declined one moves no money, and prefilling it would put a
# purchase that never happened one tap from being posted.
CARD_ALERT = re.compile(
    rf"\b({CURRENCY_NC})\s*{AMOUNT_GROUPED}\s+"
    r"([A-Za-z][A-Za-z/&.\- ]{0,40}?)\s+approved\s+"
    r"with\s+([*xX\d]{4,})",
    re.IGNORECASE,
)

# Money coming back. The wording is identical up to the descriptor.
CARD_RETURNING = re.compile(r"refund|reversal|return|credit", re.IGNORECASE)

# Where it was spent. Digits allowed — a phone order names its merchant by
# number. Ends at the time, so the name does not run on into the date.
CARD_LOCATION = re.compile(r"\bat\s+([^\n]{2,60}?)\s+on\s+\d{1,2}:\d{2}", re.IGNORECASE)

# "01:35 26.08.26" — time first, then a day-first dotted date.
TIMESTAMP_DOTTED = re.compile(
    r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\s+(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b"
)

# A name runs to a bracket, "at", "was", a digit, a full stop or the end. The
# digit terminator is load-bearing: a merchant payment puts the till code mid
# sentence ("to AFRICA BUSINESS SERVICES Limit 999577 was completed"), and
# without it the name cannot end and the whole message parses as nothing.
PARTY_TAIL = r"([^()\d.]{2,60}?)\s*(?:\(|\bat\b|\bwas\b|\d|\.|$)"

# The till or merchant code a payment quotes after the name.
MERCHANT_CODE = re.compile(
    r"\bto\s+[^()\d.]{2,60}?\s*(\d{4,12})\b(?=[^.]*?\bwas\s+completed\b|[^.]*?\bat\b)",
    re.IGNORECASE,
)

# Money moving between the user's own accounts, checked before the outgoing
# patterns: "transferred to your bank account" would otherwise read as money
# leaving. Only claimed when the message says "your" — a payment to a person
# who happens to be you looks like any other payment, and guessing misfiles it.
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
    # A direct debit, worded from the merchant's side: "by" rather than "to",
    # but the money still leaves.
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
# quotes. A MoMo message naming a bank as the other end is still a MoMo message.
MOMO_MARKERS = (
    re.compile(r"\*1(?:65|82|85)\*"),          # MTN and Airtel USSD codes
    # How a merchant payment identifies itself when the USSD prefix is absent.
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

    MoMo wins outright: its messages routinely name a bank as the other end,
    and reading that as a bank message picks the wrong account on every top-up.
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
    # Kept apart from the name so it stays recognisable later.
    merchant_code: str | None = None
    # As the message wrote them; only the API holds the stored identifiers to
    # match against.
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
        # A number never contains meaningful whitespace.
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

    The type is left provisional: "TRANSFER" in a bank message means money
    moved, not that it moved between two accounts the user owns.
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
            # were the only thing reporting one.
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
        # A bank calls it a transfer whoever the beneficiary is; resolved later.
        result.transaction_type = "TRANSFER"
        result.matched.append("transfer")
    elif credited and not debited:
        result.transaction_type = "INCOME"
    else:
        # A bill payment names both ends, but the credited one is a meter or a
        # till; resolve_accounts settles it against the user's real accounts.
        result.transaction_type = "EXPENSE"


def _read_card_alert(text: str, result: ParsedSms) -> None:
    """Read a card authorisation alert.

    The card is recorded as an account identifier so it resolves the same way a
    statement's account number does.
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

    # Which end the card is depends on which way the money went.
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

    # Both are unambiguous where prose is not, so they run first and the
    # sentence patterns are skipped when either succeeds.
    _read_labelled(text, result)
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

    # Its own ledger line, never folded into the amount above.
    fee = FEE.search(text)
    if fee:
        result.fee_amount = _decimal(fee.group(1))
        # "Fee 0 RWF" matches and yields nothing; claiming it was filled is a
        # lie the screen repeats.
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
                # Naive: sender-local, anchored by the caller like a typed date.
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
        # A kind rather than an account: only the client knows what exists.
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
        # Seconds kept: the form displays minutes but submits this.
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

# Enough to be sure without demanding the whole number: either side may be
# masked down to a tail.
MATCH_DIGITS = 4


def _digits(value: str | None) -> str:
    return "".join(c for c in (value or "") if c.isdigit())


def match_account(identifier: str | None, accounts) -> object | None:
    """The user's account this number refers to, if exactly one does.

    Trailing digits, since a message and a stored identifier rarely agree on
    masking. Ambiguity returns nothing: the wrong account is worse than none.
    """
    tail = _digits(identifier)
    if len(tail) < MATCH_DIGITS:
        return None
    tail = tail[-MATCH_DIGITS:]

    hits = [a for a in accounts if _digits(a.account_identifier).endswith(tail)]
    return hits[0] if len(hits) == 1 else None


def _currency_conversion(parsed: ParsedSms, account, converter) -> dict | None:
    """The message's amount restated in the account's own currency.

    A ledger entry is always in its account's currency, so a dollar figure
    texted about a franc card would otherwise record ten francs for a ten
    dollar purchase. A starting point only: this is the daily market rate,
    while the bank's own rate and margin are on the statement. Both figures
    are returned rather than one swapped in, so the form can say as much.
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
        # None when no rate is known; the mismatch is still worth reporting.
        "amount": serialize_amount(converted) if converted is not None else None,
        "rate": str(rate) if rate is not None else None,
    }


def resolve_accounts(parsed: ParsedSms, accounts, converter=None) -> dict:
    """Turn the message's account numbers into the user's accounts.

    This settles the type: it is a transfer in this ledger only when both ends
    are the user's. One end means money genuinely left or arrived.
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
        # The account the entry lands on owns the currency it must be in.
        "currency_conversion": _currency_conversion(
            parsed, source if source is not None else destination, converter
        ),
    }
