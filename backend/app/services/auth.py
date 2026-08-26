"""Registration, login, session lifecycle and default data provisioning."""

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.errors import Conflict, InvalidCredentials
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    validate_password_policy,
    verify_password,
)
from app.core.timezone import validate_timezone
from app.db.base import utcnow
from app.db.enums import UserStatus
from app.models.user import Session, User, UserPreference
from app.services.categories import create_default_categories


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register_user(
    db: DbSession,
    *,
    email: str,
    password: str,
    display_name: str | None,
    base_currency: str,
    timezone: str,
) -> User:
    validate_password_policy(password, email=email)
    validate_timezone(timezone)
    user = User(
        email=normalize_email(email),
        password_hash=hash_password(password),
        display_name=display_name,
        base_currency=base_currency.upper(),
        timezone=timezone,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(
            "An account with that email already exists.", code="EMAIL_ALREADY_EXISTS"
        ) from exc

    # Phase 3: preferences and default categories exist from the first moment.
    db.add(UserPreference(user_id=user.id))
    create_default_categories(db, user_id=user.id)
    db.flush()
    return user


def authenticate(db: DbSession, *, email: str, password: str) -> User:
    """Verify credentials without revealing whether the email exists."""
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        # Spend comparable time so absence is not detectable by timing.
        hash_password(password)
        raise InvalidCredentials()
    if not verify_password(user.password_hash, password):
        raise InvalidCredentials()
    if user.status is not UserStatus.ACTIVE:
        raise InvalidCredentials()
    user.last_login_at = utcnow()
    return user


def create_session(db: DbSession, user: User) -> tuple[Session, str]:
    """Return the session row and the raw token; only the hash is persisted."""
    token = generate_session_token()
    session = Session(
        user_id=user.id,
        token_hash=hash_session_token(token),
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
        last_used_at=utcnow(),
    )
    db.add(session)
    db.flush()
    return session, token


def resolve_session(db: DbSession, token: str) -> Session | None:
    session = db.scalar(select(Session).where(Session.token_hash == hash_session_token(token)))
    if session is None or session.revoked_at is not None:
        return None
    if session.expires_at <= utcnow():
        return None
    session.last_used_at = utcnow()
    return session


def revoke_session(db: DbSession, session_id: uuid.UUID) -> None:
    session = db.get(Session, session_id)
    if session is not None and session.revoked_at is None:
        session.revoked_at = utcnow()
