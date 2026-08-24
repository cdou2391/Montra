"""Shared FastAPI dependencies."""

import uuid
from collections.abc import Iterator

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.errors import AuthenticationRequired, ValidationFailed
from app.db.session import get_db
from app.models.user import Session, User
from app.services.auth import resolve_session


def db_session() -> Iterator[DbSession]:
    yield from get_db()


def current_session(
    db: DbSession = Depends(db_session),
    montra_session: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> Session:
    if not montra_session:
        raise AuthenticationRequired()
    session = resolve_session(db, montra_session)
    if session is None:
        raise AuthenticationRequired("Session is invalid or has expired.")
    return session


def current_user(
    db: DbSession = Depends(db_session),
    session: Session = Depends(current_session),
) -> User:
    user = db.get(User, session.user_id)
    if user is None:
        raise AuthenticationRequired()
    return user


def parse_uuid(value: str | None, field: str) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValidationFailed(
            details=[{"field": field, "message": "Must be a valid identifier."}]
        ) from exc
