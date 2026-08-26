"""What counts as an acceptable password.

Length does more work than composition rules. A twelve-character passphrase
resists guessing far better than "P@ss1!" while being something a person can
actually remember, so the floor is length and the rest of the checks only
remove passwords that are guessable regardless of how long they are.

Nothing here rejects a password for lacking a symbol. Rules of that shape push
people towards a small set of predictable substitutions, which is how "Passw0rd!"
became one of the most common passwords in the world.
"""

import re
import unicodedata

from app.core.errors import ValidationFailed

MINIMUM_LENGTH = 12
MAXIMUM_LENGTH = 256

# The word underneath a password, once the digits people tack on the end are
# taken away. "password1234" and "Passw0rd!!" are the same password wearing
# different hats, and an exact-match list catches neither.
#
# Deliberately short: a guard against the obvious, not a substitute for a
# breach corpus. Checking against one of those is the real answer and belongs
# with the rest of the production work.
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


# The substitutions people reach for when a rule demands a digit or a symbol.
# Undoing them is what makes "Passw0rd!" and "P@ssword" the same guess as
# "password", which is exactly how an attacker treats them.
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
    # Compare case- and accent-insensitively so "Passw0rd" is caught alongside
    # "password", and a Unicode variant does not slip past the list.
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

    Called on registration and on any change. Existing passwords are never
    re-checked: locking someone out of their own ledger over a rule that did
    not exist when they signed up would be a worse outcome than the weak
    password.
    """
    if password is None or len(password) < MINIMUM_LENGTH:
        _fail(f"Use at least {MINIMUM_LENGTH} characters. A short phrase works well.")

    if len(password) > MAXIMUM_LENGTH:
        # Argon2 will happily hash a megabyte; there is no reason to let it.
        _fail(f"Use at most {MAXIMUM_LENGTH} characters.")

    folded = _normalise(password)

    # Strip everything that is not a letter first: the digits and punctuation
    # people append are decoration, and judging the password with them left on
    # lets "password1234" through.
    # Two readings, because one alone misses half the cases.
    #
    # Dropping the digits outright turns "password1234" back into "password" —
    # but it turns "passw0rd" into "passwrd", which matches nothing. Undoing
    # the substitutions instead recovers "password" from "passw0rd" — but it
    # also invents letters out of the digits people append, so an exact match
    # no longer works and the base has to be found inside the result.
    bare = "".join(c for c in folded if c.isalpha())
    if bare in COMMON_BASES:
        _fail("That password is too easy to guess. Try a phrase of a few words.")

    unleet = "".join(c for c in folded.translate(LEET) if c.isalpha())
    for base in COMMON_BASES:
        # Proportion, not presence: a passphrase may legitimately contain
        # "secret" or "money" without being one of these. It is only the same
        # password wearing a hat when the word is most of what is there.
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
    local part of other@example.com, and there is nothing wrong with that
    password. What matters is whether the address *is* the password — as the
    whole thing, as a standalone word, or as most of the letters.
    """
    address = email.strip().casefold()
    if address and address in folded:
        _fail("Leave your email address out of your password.")

    local = address.split("@")[0]
    if len(local) < 4:
        # Too short to mean anything; "ann" would match half the dictionary.
        return

    if re.search(rf"(?<![a-z]){re.escape(local)}(?![a-z])", folded):
        _fail("Leave your email address out of your password.")

    # Proportion, but only of something that is actually there. Comparing the
    # length of the address to the length of the password on its own rejects
    # any password shorter than twice the address, however unrelated — which
    # is a rule about arithmetic, not about the password.
    letters = "".join(c for c in folded if c.isalpha())
    local_letters = "".join(c for c in local if c.isalpha())
    if local_letters and local_letters in letters and len(local_letters) >= 0.5 * len(letters):
        _fail("Leave your email address out of your password.")
