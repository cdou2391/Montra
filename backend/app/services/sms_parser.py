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

TIMESTAMP = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)")
FEE = re.compile(rf"fee[:\s]*{AMOUNT}\s*{CURRENCY}?", re.IGNORECASE)
BALANCE = re.compile(rf"(?:new\s+)?balance[:\s]*{AMOUNT}\s*{CURRENCY}?", re.IGNORECASE)
REFERENCE = re.compile(
    r"(?:financial\s+transaction\s+id|ft\s*id|transaction\s+id|txn\s*id|ref(?:erence)?)"
    r"[:\s]*([A-Za-z0-9]+)",
    re.IGNORECASE,
)

# A counterparty runs to the phone number, the timestamp, or a full stop —
# whichever comes first. Names carry spaces and mixed case, so the boundary
# has to be something other than whitespace.
PARTY_TAIL = r"([^()\d.]{2,60}?)\s*(?:\(|\bat\b|\.|$)"

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
    amount: Decimal | None = None
    currency: str | None = None
    fee_amount: Decimal | None = None
    occurred_at: datetime | None = None
    counterparty: str | None = None
    balance_after: Decimal | None = None
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
        value = Decimal(raw.replace(",", "").strip())
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


def parse(message: str) -> ParsedSms:
    """Read what the message plainly says, and nothing more."""
    result = ParsedSms()
    if not message or not message.strip():
        return result

    text = message.strip()
    result.channel = _channel(text)
    if result.channel:
        result.matched.append("account")

    for kind, patterns in (("TRANSFER", TRANSFERS), ("EXPENSE", OUTGOING), ("INCOME", INCOMING)):
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
        result.matched.append("fee")

    balance = BALANCE.search(text)
    if balance:
        result.balance_after = _decimal(balance.group(1))
        result.matched.append("balance")

    stamp = TIMESTAMP.search(text)
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
        "reference": parsed.reference,
        "matched": parsed.matched,
    }
