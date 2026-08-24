"""Celery application.

Phases 0-7 need the worker and scheduler to boot and connect to Redis. The
reminder and recurrence jobs they will run arrive in Phases 12-14.
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery("montra", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)

celery_app.conf.beat_schedule = {}


@celery_app.task(name="montra.ping")
def ping() -> str:
    """Smoke-test task proving the worker path end to end."""
    return "pong"
