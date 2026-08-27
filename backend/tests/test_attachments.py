"""Attachments.

The bytes live in object storage, so these tests stand in a fake bucket in its
place. What is being checked here is not S3 — it is that authorization happens
before a link is minted, that a link is never permanent, and that a row cannot
claim a file which was never uploaded.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.enums import TransactionType, Visibility
from app.services import attachments as attachment_service
from app.services import transactions as txn_service

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


class FakeBucket:
    """Enough of object storage to test the flow around it."""

    def __init__(self):
        self.objects: dict[str, int] = {}
        self.signed: list[tuple[str, str]] = []

    def ensure_bucket(self):
        pass

    def build_key(self, *, user_id, file_name):
        return f"attachments/{user_id}/{uuid.uuid4()}.jpg"

    def signed_upload_url(self, *, key, content_type):
        self.signed.append(("put", key))
        return {"url": f"https://bucket.test/{key}?sig=abc", "method": "PUT", "headers": {}}

    def signed_download_url(self, *, key, file_name):
        self.signed.append(("get", key))
        return f"https://bucket.test/{key}?sig=xyz"

    def object_exists(self, *, key):
        return key in self.objects

    def object_size(self, *, key):
        return self.objects.get(key)

    def delete_object(self, *, key):
        self.objects.pop(key, None)

    # Test-only: pretend the browser finished its PUT.
    def upload(self, key, size=1024):
        self.objects[key] = size


@pytest.fixture
def bucket(monkeypatch):
    fake = FakeBucket()
    monkeypatch.setattr(attachment_service, "storage", fake)
    return fake


@pytest.fixture
def transaction(db, user, bank_account):
    txn = txn_service.create_transaction(
        db,
        user=user,
        account_id=bank_account.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("12000"),
        occurred_at=NOW,
        description="Simba Supermarket",
    )
    db.commit()
    return txn


def _request(db, user, transaction, **kw):
    return attachment_service.request_upload(
        db,
        user=user,
        transaction_id=transaction.id,
        file_name=kw.pop("file_name", "receipt.jpg"),
        mime_type=kw.pop("mime_type", "image/jpeg"),
        file_size=kw.pop("file_size", 1024),
    )


# ---------------------------------------------------------------- the happy path


def test_requesting_an_upload_returns_a_link_and_a_row(db, user, transaction, bucket):
    attachment, upload = _request(db, user, transaction)
    db.commit()
    assert upload["url"].startswith("https://bucket.test/")
    assert attachment.transaction_id == transaction.id
    assert attachment.uploaded_at is None


def test_an_unconfirmed_attachment_is_not_listed(db, user, transaction, bucket):
    """A row before the bytes arrive is a promise, not a file."""
    _request(db, user, transaction)
    db.commit()
    assert attachment_service.list_for_transaction(
        db, user=user, transaction_id=transaction.id
    ) == []


def test_completing_the_upload_makes_it_real(db, user, transaction, bucket):
    attachment, _ = _request(db, user, transaction)
    db.commit()
    bucket.upload(attachment.storage_key)
    attachment_service.confirm_upload(db, user=user, attachment_id=attachment.id)
    db.commit()
    listed = attachment_service.list_for_transaction(
        db, user=user, transaction_id=transaction.id
    )
    assert [a.file_name for a in listed] == ["receipt.jpg"]


def test_completing_twice_is_harmless(db, user, transaction, bucket):
    attachment, _ = _request(db, user, transaction)
    db.commit()
    bucket.upload(attachment.storage_key)
    first = attachment_service.confirm_upload(db, user=user, attachment_id=attachment.id)
    db.commit()
    again = attachment_service.confirm_upload(db, user=user, attachment_id=attachment.id)
    assert again.uploaded_at == first.uploaded_at


def test_the_recorded_size_comes_from_the_bucket_not_the_client(db, user, transaction, bucket):
    """The size sent up front is a claim; the bucket knows the truth."""
    attachment, _ = _request(db, user, transaction, file_size=1024)
    db.commit()
    bucket.upload(attachment.storage_key, size=4096)
    confirmed = attachment_service.confirm_upload(db, user=user, attachment_id=attachment.id)
    assert confirmed.file_size == 4096


# ------------------------------------------------------------------- what is refused


def test_a_row_cannot_claim_a_file_that_never_arrived(db, user, transaction, bucket):
    attachment, _ = _request(db, user, transaction)
    db.commit()
    with pytest.raises(Conflict) as exc:
        attachment_service.confirm_upload(db, user=user, attachment_id=attachment.id)
    assert exc.value.code == "UPLOAD_NOT_FOUND"


def test_an_unsupported_type_is_refused_before_a_link_exists(db, user, transaction, bucket):
    with pytest.raises(ValidationFailed) as exc:
        _request(db, user, transaction, mime_type="application/x-msdownload")
    assert exc.value.code == "UNSUPPORTED_MEDIA_TYPE"
    assert bucket.signed == []


def test_an_oversized_claim_is_refused_before_a_link_exists(db, user, transaction, bucket):
    with pytest.raises(ValidationFailed) as exc:
        _request(db, user, transaction, file_size=50 * 1024 * 1024)
    assert exc.value.code == "FILE_TOO_LARGE"
    assert bucket.signed == []


def test_a_file_that_lied_about_its_size_is_thrown_away(db, user, transaction, bucket):
    """The claim passed; the object did not. It does not get to stay."""
    attachment, _ = _request(db, user, transaction, file_size=1024)
    db.commit()
    key = attachment.storage_key
    bucket.upload(key, size=50 * 1024 * 1024)
    with pytest.raises(ValidationFailed) as exc:
        attachment_service.confirm_upload(db, user=user, attachment_id=attachment.id)
    assert exc.value.code == "FILE_TOO_LARGE"
    assert key not in bucket.objects


# ----------------------------------------------------------------- authorization


def test_you_cannot_attach_to_someone_elses_transaction(db, user, other_user, transaction, bucket):
    with pytest.raises(NotFound):
        _request(db, other_user, transaction)
    assert bucket.signed == []


def test_a_stranger_cannot_download_your_receipt(db, user, other_user, transaction, bucket):
    attachment, _ = _request(db, user, transaction)
    db.commit()
    bucket.upload(attachment.storage_key)
    attachment_service.confirm_upload(db, user=user, attachment_id=attachment.id)
    db.commit()
    with pytest.raises(NotFound):
        attachment_service.download_url(db, user=other_user, attachment_id=attachment.id)


def test_a_stranger_cannot_delete_your_receipt(db, user, other_user, transaction, bucket):
    attachment, _ = _request(db, user, transaction)
    db.commit()
    with pytest.raises(NotFound):
        attachment_service.delete_attachment(db, user=other_user, attachment_id=attachment.id)


def test_a_household_member_can_read_a_receipt_on_a_shared_account(
    db, user, other_user, family, bank_account, transaction, bucket
):
    """Sharing an account shares its history, receipts included."""
    from app.services import accounts as account_service

    account_service.set_visibility(
        db, account=bank_account, user=user, visibility=Visibility.SHARED
    )
    attachment, _ = _request(db, user, transaction)
    db.commit()
    bucket.upload(attachment.storage_key)
    attachment_service.confirm_upload(db, user=user, attachment_id=attachment.id)
    db.commit()

    url = attachment_service.download_url(db, user=other_user, attachment_id=attachment.id)
    assert url.startswith("https://bucket.test/")


def test_reading_a_shared_receipt_is_not_deleting_it(
    db, user, other_user, family, bank_account, transaction, bucket
):
    """Visible is not editable — the same rule the accounts follow."""
    from app.services import accounts as account_service

    account_service.set_visibility(
        db, account=bank_account, user=user, visibility=Visibility.SHARED
    )
    attachment, _ = _request(db, user, transaction)
    db.commit()
    with pytest.raises(NotFound):
        attachment_service.delete_attachment(db, user=other_user, attachment_id=attachment.id)


# ----------------------------------------------------------------------- deletion


def test_deleting_removes_the_object_and_hides_the_row(db, user, transaction, bucket):
    attachment, _ = _request(db, user, transaction)
    db.commit()
    key = attachment.storage_key
    bucket.upload(key)
    attachment_service.confirm_upload(db, user=user, attachment_id=attachment.id)
    db.commit()

    attachment_service.delete_attachment(db, user=user, attachment_id=attachment.id)
    db.commit()
    assert key not in bucket.objects
    assert attachment_service.list_for_transaction(
        db, user=user, transaction_id=transaction.id
    ) == []


def test_a_deleted_attachment_is_gone_for_good(db, user, transaction, bucket):
    attachment, _ = _request(db, user, transaction)
    db.commit()
    attachment_service.delete_attachment(db, user=user, attachment_id=attachment.id)
    db.commit()
    with pytest.raises(NotFound):
        attachment_service.download_url(db, user=user, attachment_id=attachment.id)


# ---------------------------------------------------------------------- payload


def test_the_storage_key_never_reaches_the_client(db, user, transaction, bucket):
    """It is the input to a signed URL, not a URL — and not the client's."""
    attachment, _ = _request(db, user, transaction)
    payload = attachment_service.serialize(attachment)
    assert "storage_key" not in payload
    assert attachment.storage_key not in str(payload)


# --------------------------------------------------------------------- transfers


@pytest.fixture
def transfer(db, user, bank_account, savings_account):
    from app.services.posting import PostingService

    moved = PostingService(db).transfer_funds(
        source=bank_account,
        destination=savings_account,
        source_amount=Decimal("40000"),
        destination_amount=Decimal("40000"),
        occurred_at=NOW,
        actor_id=user.id,
    )
    db.commit()
    return moved


def _transfer_upload(db, user, transfer, **kw):
    return attachment_service.request_upload_for_transfer(
        db,
        user=user,
        transfer_id=transfer.id,
        file_name=kw.pop("file_name", "proof.pdf"),
        mime_type=kw.pop("mime_type", "application/pdf"),
        file_size=kw.pop("file_size", 2048),
    )


def test_proof_of_payment_lands_on_the_outgoing_side(db, user, transfer, bucket):
    attachment, _ = _transfer_upload(db, user, transfer)
    db.commit()
    from app.models.finance import Transaction

    side = db.get(Transaction, attachment.transaction_id)
    assert side.account_id == transfer.source_account_id


def test_a_transfers_receipt_is_visible_from_either_side(db, user, transfer, bucket):
    """The receipt describes the movement, not one leg of it."""
    from sqlalchemy import select as sa_select

    from app.models.finance import Transaction

    attachment, _ = _transfer_upload(db, user, transfer)
    db.commit()
    bucket.upload(attachment.storage_key)
    attachment_service.confirm_upload(db, user=user, attachment_id=attachment.id)
    db.commit()

    legs = list(
        db.scalars(sa_select(Transaction).where(Transaction.transfer_id == transfer.id))
    )
    assert len(legs) == 2
    for leg in legs:
        found = attachment_service.list_for_transaction(
            db, user=user, transaction_id=leg.id
        )
        assert [a.file_name for a in found] == ["proof.pdf"]


def test_a_stranger_cannot_attach_to_your_transfer(db, user, other_user, transfer, bucket):
    with pytest.raises(NotFound):
        _transfer_upload(db, other_user, transfer)
    assert bucket.signed == []


def test_attaching_to_a_transfer_that_does_not_exist(db, user, bucket):
    class Missing:
        id = uuid.uuid4()

    with pytest.raises(NotFound):
        _transfer_upload(db, user, Missing())
