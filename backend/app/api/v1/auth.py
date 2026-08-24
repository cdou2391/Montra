"""Authentication and preference endpoints (API spec sections 13-14)."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_session, current_user, db_session
from app.core.config import settings
from app.core.responses import single
from app.models.user import Session, User, UserPreference
from app.schemas.auth import (
    BackupRestoreRequest,
    LoginRequest,
    PreferencesUpdate,
    ProfileResetRequest,
    RegisterRequest,
)
from app.services import auth as auth_service
from app.services import backup as backup_service
from app.services import profile as profile_service

router = APIRouter(tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def _user_payload(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "base_currency": user.base_currency,
        "timezone": user.timezone,
    }


def _preferences_payload(prefs: UserPreference) -> dict:
    return {
        "hide_balances": prefs.hide_balances,
        "persist_balance_privacy": prefs.persist_balance_privacy,
        "default_context": prefs.default_context.value,
        "default_reminder_days": prefs.default_reminder_days,
        "notifications_enabled": prefs.notifications_enabled,
    }


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    db: DbSession = Depends(db_session),
) -> dict:
    user = auth_service.register_user(
        db,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        base_currency=payload.base_currency,
        timezone=payload.timezone,
    )
    _, token = auth_service.create_session(db, user)
    db.commit()
    _set_session_cookie(response, token)
    return single(_user_payload(user))


@router.post("/auth/login")
def login(
    payload: LoginRequest,
    response: Response,
    db: DbSession = Depends(db_session),
) -> dict:
    user = auth_service.authenticate(db, email=payload.email, password=payload.password)
    _, token = auth_service.create_session(db, user)
    db.commit()
    _set_session_cookie(response, token)
    return single({"user": _user_payload(user)})


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: DbSession = Depends(db_session),
    session: Session = Depends(current_session),
) -> Response:
    auth_service.revoke_session(db, session.id)
    db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/me")
def me(
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    db.commit()  # persist last_used_at touch from session resolution
    payload = _user_payload(user)
    payload["active_family"] = None  # Family arrives in Phase 16
    return single(payload)


@router.get("/preferences")
def get_preferences(
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    db.commit()
    return single(_preferences_payload(user.preferences))


@router.patch("/preferences")
def update_preferences(
    payload: PreferencesUpdate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    prefs = user.preferences
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(prefs, field, value)
    db.commit()
    db.refresh(prefs)
    return single(_preferences_payload(prefs))


@router.get("/profile/reset-preview")
def reset_preview(
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """What a reset would delete, so the warning can name real numbers."""
    summary = profile_service.reset_summary(db, user)
    db.commit()
    return single(summary)


@router.post("/profile/reset")
def reset_profile(
    payload: ProfileResetRequest,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """Delete every financial record and start fresh. Irreversible.

    The login survives, so this is "start over", not "delete my account".
    """
    deleted = profile_service.reset_profile(db, user=user, password=payload.password)
    db.commit()
    return single({"deleted": deleted})


@router.get("/profile/backup")
def download_backup(
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> Response:
    """Every financial record this user owns, as a downloadable document.

    Served as an attachment with a dated filename, because a backup that lands
    in a browser tab is not a backup.
    """
    import json

    payload = backup_service.export_backup(db, user)
    db.commit()
    stamp = payload["exported_at"][:10]
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="montra-backup-{stamp}.json"',
        },
    )


@router.post("/profile/restore")
def restore_backup(
    payload: BackupRestoreRequest,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """Replace everything with the contents of a backup. Irreversible."""
    restored = backup_service.restore_backup(
        db, user=user, payload=payload.backup, password=payload.password
    )
    db.commit()
    return single({"restored": restored})
