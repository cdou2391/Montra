"""Receipts and documents attached to a transaction (Phase 27).

The flow the plan asks for:

    API authorization → signed upload → object storage → metadata

Authorization happens first and here, not at the bucket. The client never
learns a storage key and never receives a permanent URL; every read is a fresh
signed link with minutes on the clock.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.base import utcnow
from app.models.records import Attachment
from app.models.user import User
from app.services import audit, storage
from app.services.authz import get_transactable_account
from app.services.transactions import get_transaction

MAX_FILE_NAME = 255


def _validate(*, file_name: str, mime_type: str, file_size: int) -> None:
    if not file_name.strip():
        raise ValidationFailed(
            details=[{"field": "file_name", "message": "A file name is required."}]
        )
    if len(file_name) > MAX_FILE_NAME:
        raise ValidationFailed(
            details=[{"field": "file_name", "message": "That file name is too long."}]
        )
    if mime_type not in settings.attachment_mime_list:
        raise ValidationFailed(
            "That kind of file cannot be attached.",
            code="UNSUPPORTED_MEDIA_TYPE",
            details=[{"field": "mime_type", "message": "Images and PDFs only."}],
        )
    if file_size <= 0 or file_size > settings.attachment_max_bytes:
        megabytes = settings.attachment_max_bytes // (1024 * 1024)
        raise ValidationFailed(
            f"Attachments must be smaller than {megabytes}MB.",
            code="FILE_TOO_LARGE",
            details=[{"field": "file_size", "message": f"Maximum {megabytes}MB."}],
        )


def request_upload(
    db: DbSession,
    *,
    user: User,
    transaction_id: uuid.UUID,
    file_name: str,
    mime_type: str,
    file_size: int,
) -> tuple[Attachment, dict]:
    """Authorize, then hand back a link the browser can upload to.

    The row is written before the bytes arrive, deliberately: it is what makes
    the later "did it land?" check possible, and what stops an upload URL from
    existing without a record of who asked for it. Until `uploaded_at` is set
    the attachment is a promise and is not listed.
    """
    _validate(file_name=file_name, mime_type=mime_type, file_size=file_size)

    # Attaching to a transaction writes to it, so the test is the same one the
    # transaction's own edits use: being allowed to see a shared account is not
    # being allowed to add to it.
    transaction = get_transaction(db, transaction_id, user)
    get_transactable_account(db, transaction.account_id, user)

    key = storage.build_key(user_id=user.id, file_name=file_name)
    attachment = Attachment(
        user_id=user.id,
        transaction_id=transaction.id,
        file_name=file_name.strip(),
        storage_key=key,
        mime_type=mime_type,
        file_size=file_size,
    )
    db.add(attachment)
    db.flush()

    storage.ensure_bucket()
    return attachment, storage.signed_upload_url(key=key, content_type=mime_type)


def confirm_upload(db: DbSession, *, user: User, attachment_id: uuid.UUID) -> Attachment:
    """Mark an attachment usable, once the object is really there.

    Trusting the client's word would let a row claim a file that was never
    uploaded, so the bucket is asked directly. The recorded size comes from the
    bucket too — the size sent up front was only ever a claim used to reject
    obviously oversized uploads early.
    """
    attachment = _own_attachment(db, user=user, attachment_id=attachment_id)
    if attachment.uploaded_at is not None:
        return attachment

    if not storage.object_exists(key=attachment.storage_key):
        raise Conflict(
            "The file has not finished uploading.",
            code="UPLOAD_NOT_FOUND",
        )

    actual = storage.object_size(key=attachment.storage_key)
    if actual is not None:
        if actual > settings.attachment_max_bytes:
            storage.delete_object(key=attachment.storage_key)
            db.delete(attachment)
            db.flush()
            megabytes = settings.attachment_max_bytes // (1024 * 1024)
            raise ValidationFailed(
                f"Attachments must be smaller than {megabytes}MB.",
                code="FILE_TOO_LARGE",
                details=[{"field": "file_size", "message": f"Maximum {megabytes}MB."}],
            )
        attachment.file_size = actual

    attachment.uploaded_at = utcnow()
    db.flush()
    audit.record(
        db,
        actor=user,
        event_type=audit.ATTACHMENT_ADDED,
        entity_type=audit.ATTACHMENT,
        entity_id=attachment.id,
        metadata={"transaction_id": str(attachment.transaction_id)},
    )
    return attachment


def list_for_transaction(
    db: DbSession, *, user: User, transaction_id: uuid.UUID
) -> list[Attachment]:
    """Everything attached to a transaction the user may see."""
    get_transaction(db, transaction_id, user)
    return list(
        db.scalars(
            select(Attachment)
            .where(
                Attachment.transaction_id == transaction_id,
                Attachment.deleted_at.is_(None),
                Attachment.uploaded_at.is_not(None),
            )
            .order_by(Attachment.created_at)
        )
    )


def download_url(db: DbSession, *, user: User, attachment_id: uuid.UUID) -> str:
    attachment = _viewable_attachment(db, user=user, attachment_id=attachment_id)
    if attachment.uploaded_at is None:
        raise NotFound("Attachment not found.", code="ATTACHMENT_NOT_FOUND")
    return storage.signed_download_url(
        key=attachment.storage_key, file_name=attachment.file_name
    )


def delete_attachment(db: DbSession, *, user: User, attachment_id: uuid.UUID) -> None:
    """Remove the file and tombstone the row.

    The object goes for real — a receipt someone deleted should not linger in a
    bucket — while the row is kept as a tombstone so the audit trail still has
    something to point at.
    """
    attachment = _own_attachment(db, user=user, attachment_id=attachment_id)
    storage.delete_object(key=attachment.storage_key)
    attachment.deleted_at = utcnow()
    db.flush()
    # The file is gone from the bucket for real, so this is the only record
    # that it was ever there.
    audit.record(
        db,
        actor=user,
        event_type=audit.ATTACHMENT_DELETED,
        entity_type=audit.ATTACHMENT,
        entity_id=attachment.id,
        metadata={"transaction_id": str(attachment.transaction_id)},
    )


def _own_attachment(db: DbSession, *, user: User, attachment_id: uuid.UUID) -> Attachment:
    """An attachment the user may change — theirs, and not already gone."""
    attachment = db.get(Attachment, attachment_id)
    if attachment is None or attachment.deleted_at is not None or attachment.user_id != user.id:
        # 404 rather than 403: someone else's attachment should not be
        # distinguishable from one that never existed.
        raise NotFound("Attachment not found.", code="ATTACHMENT_NOT_FOUND")
    return attachment


def _viewable_attachment(db: DbSession, *, user: User, attachment_id: uuid.UUID) -> Attachment:
    """An attachment the user may read.

    Not the same question as ownership: a receipt on a shared account is
    readable by the household, and the transaction's own visibility rules are
    the authority on that.
    """
    attachment = db.get(Attachment, attachment_id)
    if attachment is None or attachment.deleted_at is not None:
        raise NotFound("Attachment not found.", code="ATTACHMENT_NOT_FOUND")
    if attachment.user_id != user.id:
        if attachment.transaction_id is None:
            raise NotFound("Attachment not found.", code="ATTACHMENT_NOT_FOUND")
        # Raises NotFound itself if the transaction is not visible.
        get_transaction(db, attachment.transaction_id, user)
    return attachment


def serialize(attachment: Attachment) -> dict:
    """Metadata only. The storage key never leaves the server."""
    return {
        "id": str(attachment.id),
        "transaction_id": (
            str(attachment.transaction_id) if attachment.transaction_id else None
        ),
        "file_name": attachment.file_name,
        "mime_type": attachment.mime_type,
        "file_size": attachment.file_size,
        "uploaded": attachment.uploaded_at is not None,
        "created_at": attachment.created_at.isoformat(),
    }


def uploaded_before(db: DbSession, *, cutoff: datetime) -> list[Attachment]:
    """Rows whose upload never completed, for cleaning up later."""
    return list(
        db.scalars(
            select(Attachment).where(
                Attachment.uploaded_at.is_(None),
                Attachment.deleted_at.is_(None),
                Attachment.created_at < cutoff,
            )
        )
    )
