"""Celery application, queues and scheduled tasks (Implementation Plan Phase 13).

Reminder and recurrence definitions live in PostgreSQL, never only in the
broker. If Redis is lost, nothing scheduled is lost with it: the next run of a
beat task re-reads state from the database and carries on.
"""

import logging

from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from app.core.config import settings

logger = logging.getLogger("montra.worker")

celery_app = Celery("montra", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_queues=(
        Queue("default"),
        Queue("recurring"),
        Queue("reminders"),
        Queue("notifications"),
    ),
    task_routes={
        "montra.generate_recurring_occurrences": {"queue": "recurring"},
        "montra.process_due_reminders": {"queue": "reminders"},
        "montra.refresh_planned_status": {"queue": "default"},
    },
)

celery_app.conf.beat_schedule = {
    # Keep the forward window populated. Hourly is far more often than needed
    # for a 90-day window, but the task is idempotent and cheap, and it means a
    # missed run never leaves a gap.
    "generate-recurring-occurrences": {
        "task": "montra.generate_recurring_occurrences",
        "schedule": crontab(minute=5),
    },
    "process-due-reminders": {
        "task": "montra.process_due_reminders",
        "schedule": crontab(minute="*/15"),
    },
    "refresh-planned-status": {
        "task": "montra.refresh_planned_status",
        "schedule": crontab(minute=0),
    },
    # A card expiry moves once a day at most, so once a day is enough. Early
    # morning, so the notice is waiting rather than arriving mid-evening.
    "notify-expiring-cards": {
        "task": "montra.notify_expiring_cards",
        "schedule": crontab(hour=6, minute=30),
    },
    # Published rates settle overnight; 07:00 means the day's totals are
    # already current by the time anyone opens the app.
    "refresh-exchange-rates": {
        "task": "montra.refresh_exchange_rates",
        "schedule": crontab(hour=7, minute=0),
    },
}


@celery_app.task(name="montra.ping")
def ping() -> str:
    """Smoke-test task proving the worker path end to end."""
    return "pong"


@celery_app.task(name="montra.generate_recurring_occurrences")
def generate_recurring_occurrences() -> int:
    """Materialise planned occurrences for every active rule."""
    from sqlalchemy import select

    from app.db.enums import RecurringStatus
    from app.db.session import SessionLocal
    from app.models.planning import RecurringRule
    from app.models.user import User
    from app.services.planning import generate_occurrences

    created = 0
    with SessionLocal() as db:
        rules = db.scalars(
            select(RecurringRule).where(RecurringRule.status == RecurringStatus.ACTIVE)
        ).all()
        for rule in rules:
            owner = db.get(User, rule.created_by)
            if owner is None:
                continue
            try:
                created += len(generate_occurrences(db, rule, owner=owner))
            except Exception:
                # One bad rule must not stop the rest of the run.
                logger.exception("recurrence generation failed for rule %s", rule.id)
                db.rollback()
        db.commit()
    logger.info("generated %s planned occurrences", created)
    return created


@celery_app.task(name="montra.process_due_reminders")
def process_due_reminders() -> int:
    """Turn due reminders into notifications, revalidating each one first."""
    from app.db.session import SessionLocal
    from app.services.planning import process_due_reminders as run

    with SessionLocal() as db:
        sent = run(db)
        db.commit()
    logger.info("sent %s reminder notifications", sent)
    return sent


@celery_app.task(name="montra.refresh_planned_status")
def refresh_planned_status() -> int:
    """Move UPCOMING items whose moment has passed into DUE."""
    from sqlalchemy import update

    from app.db.base import utcnow
    from app.db.enums import PlannedStatus
    from app.db.session import SessionLocal
    from app.models.planning import PlannedTransaction

    with SessionLocal() as db:
        result = db.execute(
            update(PlannedTransaction)
            .where(
                PlannedTransaction.status == PlannedStatus.UPCOMING,
                PlannedTransaction.expected_at <= utcnow(),
            )
            .values(status=PlannedStatus.DUE)
        )
        db.commit()
        count = result.rowcount or 0
    logger.info("promoted %s planned items to DUE", count)
    return count


@celery_app.task(name="montra.notify_expiring_cards")
def notify_expiring_cards() -> int:
    """Warn about cards approaching their expiry date."""
    from app.db.session import SessionLocal
    from app.services.credit_cards import notify_expiring_cards as run

    with SessionLocal() as db:
        sent = run(db)
        db.commit()
    logger.info("sent %s card expiry notifications", sent)
    return sent


@celery_app.task(name="montra.refresh_exchange_rates")
def refresh_exchange_rates() -> int:
    """Pull the day's published rates for every user who holds two currencies."""
    from app.db.session import SessionLocal
    from app.services.currency import sync_all

    with SessionLocal() as db:
        updated = sync_all(db)
        db.commit()
    logger.info("refreshed %s exchange rates", updated)
    return updated
