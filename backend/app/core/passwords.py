"""What counts as an acceptable password.

Length does more work than composition rules: a twelve-character passphrase
resists guessing better than "P@ss1!" and is rememberable. So the floor is
length, and the rest only removes passwords guessable at any length.

Nothing here demands a symbol. Rules of that shape push people towards a small
set of predictable substitutions — which is how "Passw0rd!" became one of the
most common passwords in the world.
"""

import re
import unicodedata

from app.core.errors import ValidationFailed

MINIMUM_LENGTH = 12
MAXIMUM_LENGTH = 256

# The word underneath a password once the tacked-on digits are gone:
# "password1234" and "Passw0rd!!" are one password in two hats, and an
# exact-match list catches neither. Short on purpose — a guard against the
# obvious, not a substitute for a breach corpus.
COMMON_BASES = frozenset(
    {
        "password",
        "passwd",
        "pass",
        "qwerty",
        "qwertyuiop",
        "azerty",
        "letmein",
        "welcome",
        "iloveyou",
        "admin",
        "administrator",
        "changeme",
        "montra",
        "money",
        "secret",
        "monkey",
        "dragon",
        "football",
        "sunshine",
        "princess",
        "abc",
        "test",
    }
)


# Undoing these makes "Passw0rd!" and "P@ssword" the same guess as "password",
# which is how an attacker treats them.
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t",
                      "@": "a", "$": "s", "!": "i", "|": "l"})

DIGITS = "0123456789" * 3
LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _is_a_run(folded: str) -> bool:
    """A straight walk along the keyboard or the number line.

    "123456789012" is long, has ten distinct characters, and is among the
    first things anyone would try.
    """
    if len(folded) < 6:
        return False
    for line in (DIGITS, LETTERS, "qwertyuiopasdfghjklzxcvbnm"):
        if folded in line or folded in line[::-1]:
            return True
    return False


def _normalise(password: str) -> str:
    # Case- and accent-insensitive, so a Unicode variant cannot slip past.
    folded = unicodedata.normalize("NFKD", password).casefold()
    return "".join(c for c in folded if not unicodedata.combining(c))


def _fail(message: str) -> None:
    raise ValidationFailed(
        message,
        code="WEAK_PASSWORD",
        details=[{"field": "password", "message": message}],
    )


def validate(password: str, *, email: str | None = None) -> None:
    """Raise if this password should not be accepted.

    Registration and change only. Existing passwords are never re-checked:
    locking someone out of their ledger over a rule that postdates them is
    worse than the weak password.
    """
    if password is None or len(password) < MINIMUM_LENGTH:
        _fail(f"Use at least {MINIMUM_LENGTH} characters. A short phrase works well.")

    if len(password) > MAXIMUM_LENGTH:
        # Argon2 will happily hash a megabyte.
        _fail(f"Use at most {MAXIMUM_LENGTH} characters.")

    folded = _normalise(password)

    # Two readings, because either alone misses half the cases. Dropping digits
    # turns "password1234" into "password" but "passw0rd" into "passwrd", which
    # matches nothing. Unsubstituting recovers "password" from "passw0rd" but
    # invents letters from appended digits, so it has to match on containment.
    bare = "".join(c for c in folded if c.isalpha())
    if bare in COMMON_BASES:
        _fail("That password is too easy to guess. Try a phrase of a few words.")

    unleet = "".join(c for c in folded.translate(LEET) if c.isalpha())
    for base in COMMON_BASES:
        # Proportion, not presence: a passphrase may contain "money" without
        # being it. Only most of the letters makes it the same password.
        if base in unleet and len(base) >= 0.6 * len(unleet):
            _fail("That password is too easy to guess. Try a phrase of a few words.")

    if _is_a_run(folded):
        _fail("That password runs straight along the keyboard. Try a phrase of a few words.")

    if len(set(folded)) < 4:
        # "aaaaaaaaaaaa" clears the length bar and nothing else.
        _fail("That password repeats too few characters. Try a phrase of a few words.")

    if re.fullmatch(r"(.{1,4}?)\1+", folded):
        # "abcabcabcabc" — long, and one short guess away.
        _fail("That password is a short pattern repeated. Try a phrase of a few words.")

    if email:
        _reject_own_address(folded, email)


def _reject_own_address(folded: str, email: str) -> None:
    """Catch a password that is really just the user's own address.

    A bare substring test is too eager: "another good passphrase" contains the
    local part of other@example.com and is fine. What matters is whether the
    address *is* the password — whole, as a word, or as most of the letters.
    """
    address = email.strip().casefold()
    if address and address in folded:
        _fail("Leave your email address out of your password.")

    local = address.split("@")[0]
    if len(local) < 4:
        # "ann" would match half the dictionary.
        return

    if re.search(rf"(?<![a-z]){re.escape(local)}(?![a-z])", folded):
        _fail("Leave your email address out of your password.")

    # Proportion, but only of something actually present: comparing lengths
    # alone rejects any short password, however unrelated.
    letters = "".join(c for c in folded if c.isalpha())
    local_letters = "".join(c for c in local if c.isalpha())
    if local_letters and local_letters in letters and len(local_letters) >= 0.5 * len(letters):
        _fail("Leave your email address out of your password.")
