"""Liveness and readiness endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.api.deps import db_session
from app.core.config import settings
from app.core.errors import DependencyUnavailable

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
