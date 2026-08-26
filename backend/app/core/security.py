"""Password hashing and session token generation."""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.errors import ValidationFailed

_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


def validate_password_policy(password: str, *, email: str | None = None) -> None:
    """Whether this password may be set.

    The rules live in app.core.passwords; this stays as the entry point every
    caller already uses, and keeps the PASSWORD_POLICY_FAILED code they and the
    clients expect.
    """
    from app.core.passwords import validate

    try:
        validate(password, email=email)
    except ValidationFailed as weak:
        raise ValidationFailed(
            "Password does not meet the required policy.",
            code="PASSWORD_POLICY_FAILED",
            details=weak.details,
        ) from weak



def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    """Session tokens are stored hashed so a database read cannot mint a session."""
    return hashlib.sha256(token.encode()).hexdigest()
