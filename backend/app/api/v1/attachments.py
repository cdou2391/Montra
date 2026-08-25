"""Attachment endpoints (Implementation Plan Phase 27).

Three steps, because the bytes never pass through this service: ask for a
link, upload to storage, then confirm. Reads are the same shape in reverse —
the API returns a signed URL, never a stored one.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user, db_session
from app.core.config import settings
from app.core.responses import collection, single
from app.models.user import User
from app.schemas.attachments import AttachmentCreate
from app.services import attachments as attachment_service

router = APIRouter(tags=["attachments"])


@router.post("/transactions/{transaction_id}/attachments", status_code=status.HTTP_201_CREATED)
def request_upload(
    transaction_id: uuid.UUID,
    payload: AttachmentCreate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    attachment, upload = attachment_service.request_upload(
        db,
        user=user,
        transaction_id=transaction_id,
        file_name=payload.file_name,
        mime_type=payload.mime_type,
        file_size=payload.file_size,
    )
    db.commit()
    db.refresh(attachment)
    return single({**attachment_service.serialize(attachment), "upload": upload})


@router.post("/attachments/{attachment_id}/complete")
def complete_upload(
    attachment_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    attachment = attachment_service.confirm_upload(db, user=user, attachment_id=attachment_id)
    db.commit()
    db.refresh(attachment)
    return single(attachment_service.serialize(attachment))


@router.get("/transactions/{transaction_id}/attachments")
def list_attachments(
    transaction_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    rows = attachment_service.list_for_transaction(db, user=user, transaction_id=transaction_id)
    return collection([attachment_service.serialize(a) for a in rows], limit=len(rows))


@router.get("/attachments/{attachment_id}/download")
def download(
    attachment_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    # A URL rather than a redirect: the client decides whether to open it in a
    # tab or fetch it, and the link's short life is visible to the caller.
    return single(
        {
            "url": attachment_service.download_url(db, user=user, attachment_id=attachment_id),
            "expires_in": settings.s3_signed_url_ttl_seconds,
        }
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> None:
    attachment_service.delete_attachment(db, user=user, attachment_id=attachment_id)
    db.commit()
