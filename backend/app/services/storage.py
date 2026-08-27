"""Object storage for attachments.

Files never touch Postgres and have no permanent public URL: the API authorizes,
then hands back a short-lived signed link the browser uses directly. Runs
against MinIO locally and any S3-compatible bucket in production.
"""

import uuid
from functools import lru_cache

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings


@lru_cache
def _client(*, public: bool = False):
    """A boto3 S3 client — two, in fact.

    Server-side calls use the in-network endpoint. Signed URLs must be signed
    for the hostname the *browser* will use, or the signature covers a host it
    never contacts and the request is rejected.
    """
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_public_endpoint_url if public else settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket() -> None:
    """Create the bucket if it is not there yet. Safe to call repeatedly."""
    client = _client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except ClientError:
        client.create_bucket(Bucket=settings.s3_bucket)


def build_key(*, user_id: uuid.UUID, file_name: str) -> str:
    """Where the object lives.

    Prefixed by owner so a listing cannot be walked across users, and suffixed
    with a UUID so two IMG_0001.jpg never collide.
    """
    suffix = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "bin"
    if not suffix.isalnum() or len(suffix) > 8:
        suffix = "bin"
    return f"attachments/{user_id}/{uuid.uuid4()}.{suffix}"


def signed_upload_url(*, key: str, content_type: str) -> dict:
    """A URL the browser can PUT one specific object to, once, soon.

    The content type is signed too, so a client that promised a JPEG cannot
    upload something else under the same link.
    """
    url = _client(public=True).generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=settings.s3_signed_url_ttl_seconds,
    )
    return {
        "url": url,
        "method": "PUT",
        "headers": {"Content-Type": content_type},
        "expires_in": settings.s3_signed_url_ttl_seconds,
    }


def signed_download_url(*, key: str, file_name: str) -> str:
    """A short-lived link to read one object."""
    return _client(public=True).generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": key,
            # No inline rendering, and the name the user recognises.
            "ResponseContentDisposition": f'attachment; filename="{file_name}"',
        },
        ExpiresIn=settings.s3_signed_url_ttl_seconds,
    )


def object_exists(*, key: str) -> bool:
    """Whether the upload actually landed."""
    try:
        _client().head_object(Bucket=settings.s3_bucket, Key=key)
        return True
    except ClientError:
        return False


def object_size(*, key: str) -> int | None:
    try:
        return int(_client().head_object(Bucket=settings.s3_bucket, Key=key)["ContentLength"])
    except ClientError:
        return None


def delete_object(*, key: str) -> None:
    try:
        _client().delete_object(Bucket=settings.s3_bucket, Key=key)
    except ClientError:
        # The row is going either way; a missing object is the goal.
        pass
