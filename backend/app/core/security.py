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


def validate_password_policy(password: str) -> None:
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if password.isdigit() or password.isalpha():
        problems.append("Password must mix letters with numbers or symbols.")
    if problems:
        raise ValidationFailed(
            "Password does not meet the required policy.",
            code="PASSWORD_POLICY_FAILED",
            details=[{"field": "password", "message": m} for m in problems],
        )


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    """Session tokens are stored hashed so a database read cannot mint a session."""
    return hashlib.sha256(token.encode()).hexdigest()
