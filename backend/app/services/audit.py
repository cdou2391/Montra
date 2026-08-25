"""Audit trail (Implementation Plan Phase 28).

Who did what, to which thing, when. The point is accountability in a shared
household: when an account changes hands or a transfer is cancelled, there has
to be a record that does not depend on the changed thing still existing.

Two rules shape everything here:

* Append-only. Nothing in the application updates or deletes a row.
* Metadata carries identifiers and small facts, never a copy of the financial
  record. A duplicate of the transaction would be a second, unreconciled
  ledger — and a place for sensitive detail to leak into a wider audience than
  the record itself has.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models.records import AuditEvent
from app.models.user import User

# Entity types.
ACCOUNT = "ACCOUNT"
TRANSACTION = "TRANSACTION"
TRANSFER = "TRANSFER"
FAMILY = "FAMILY"
LOAN = "LOAN"
ATTACHMENT = "ATTACHMENT"

# Event types, from Data Model section 43.
ACCOUNT_CREATED = "ACCOUNT_CREATED"
ACCOUNT_SHARED = "ACCOUNT_SHARED"
ACCOUNT_MADE_PRIVATE = "ACCOUNT_MADE_PRIVATE"
ACCOUNT_VISIBILITY_CHANGED = "ACCOUNT_VISIBILITY_CHANGED"
ACCOUNT_ARCHIVED = "ACCOUNT_ARCHIVED"
TRANSACTION_CREATED = "TRANSACTION_CREATED"
SHARED_TRANSACTION_CREATED = "SHARED_TRANSACTION_CREATED"
TRANSACTION_UPDATED = "TRANSACTION_UPDATED"
TRANSACTION_DELETED = "TRANSACTION_DELETED"
TRANSFER_CREATED = "TRANSFER_CREATED"
TRANSFER_CANCELLED = "TRANSFER_CANCELLED"
FAMILY_CREATED = "FAMILY_CREATED"
FAMILY_MEMBER_INVITED = "FAMILY_MEMBER_INVITED"
FAMILY_MEMBER_JOINED = "FAMILY_MEMBER_JOINED"
FAMILY_MEMBER_REMOVED = "FAMILY_MEMBER_REMOVED"
FAMILY_MEMBER_LEFT = "FAMILY_MEMBER_LEFT"
FAMILY_ROLE_CHANGED = "FAMILY_ROLE_CHANGED"
LOAN_PAYMENT_RECORDED = "LOAN_PAYMENT_RECORDED"
ATTACHMENT_ADDED = "ATTACHMENT_ADDED"
ATTACHMENT_DELETED = "ATTACHMENT_DELETED"

# Keys that must never appear in metadata. An audit row is read by more people
# than the record it describes — in a household, by every member — so amounts
# and free text stay out of it and live where the permissions already are.
FORBIDDEN_KEYS = frozenset(
    {
        "amount",
        "balance",
        "description",
        "notes",
        "merchant",
        "reference",
        "opening_balance",
        "statement_balance",
        "minimum_payment",
        "credit_limit",
        "password",
        "token",
        "email",
        "account_identifier",
    }
)


def record(
    db: DbSession,
    *,
    actor: User | None,
    event_type: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    family_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append one event.

    Flushed but not committed: the event belongs to the same transaction as the
    thing it describes, so a rolled-back action leaves no audit row claiming it
    happened.
    """
    if metadata:
        offending = FORBIDDEN_KEYS & set(metadata)
        if offending:
            raise ValueError(
                f"Audit metadata must not carry financial detail: {sorted(offending)}"
            )

    event = AuditEvent(
        actor_user_id=actor.id if actor else None,
        family_id=family_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        event_metadata=metadata or None,
    )
    db.add(event)
    db.flush()
    return event


def for_family(db: DbSession, *, family_id: uuid.UUID, limit: int = 50) -> list[AuditEvent]:
    """The household's recent history, newest first."""
    return list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.family_id == family_id)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
        )
    )


def for_entity(
    db: DbSession, *, entity_type: str, entity_id: uuid.UUID, limit: int = 50
) -> list[AuditEvent]:
    return list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
        )
    )


def serialize(event: AuditEvent, *, actor_names: dict[uuid.UUID, str] | None = None) -> dict:
    names = actor_names or {}
    return {
        "id": str(event.id),
        "event_type": event.event_type,
        "entity_type": event.entity_type,
        "entity_id": str(event.entity_id) if event.entity_id else None,
        "actor": (
            {
                "id": str(event.actor_user_id),
                "display_name": names.get(event.actor_user_id),
            }
            if event.actor_user_id
            else None
        ),
        "metadata": event.event_metadata,
        "created_at": event.created_at.isoformat(),
    }
