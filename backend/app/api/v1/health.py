"""Liveness, readiness, and what this build is."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.api.deps import db_session
from app.core.config import settings
from app.core.errors import DependencyUnavailable
from app.core.version import APP_NAME, APP_VERSION

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict:
    """Process is up. Deliberately touches no dependency."""
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: DbSession = Depends(db_session)) -> dict:
    """Ready to serve traffic: database and Redis both reachable."""
    checks: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        raise DependencyUnavailable("Database is unavailable.") from exc

    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        raise DependencyUnavailable("Redis is unavailable.") from exc

    return {"status": "ready", "checks": checks}


@router.get("/meta")
def meta() -> dict:
    """What this build calls itself.

    Unauthenticated, like the health endpoints beside it: the name and version
    of a running service are not a secret, and the client needs them on the
    About screen before it necessarily has a session.
    """
    return {"name": APP_NAME, "version": APP_VERSION}
