"""Optional S3-compatible off-site export for verified local database backups.

Credentials are resolved by boto3's standard provider chain (environment,
instance role, or configured profile). This module never deletes remote objects.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upload_backup(
    backup_path: str | Path,
    *,
    bucket: str,
    region: str = "us-east-1",
    prefix: str = "peak-adventure-backups",
    endpoint_url: str | None = None,
    kms_key_id: str | None = None,
    s3_client=None,
) -> str:
    """Upload one verified local backup and return its object key.

    The caller must create and verify the local backup first. Upload failures
    are raised so the scheduler can report that off-site recovery did not run.
    """
    path = Path(backup_path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError("Refusing to upload a missing or empty backup file.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        raise ValueError("OFFSITE_BACKUP_BUCKET is not a valid S3 bucket name.")
    if not isinstance(region, str) or not region.strip():
        raise ValueError("OFFSITE_BACKUP_REGION must not be empty.")
    clean_prefix = "/".join(part for part in prefix.strip("/").split("/") if part)
    if any(part in {".", ".."} for part in clean_prefix.split("/") if part):
        raise ValueError("OFFSITE_BACKUP_PREFIX contains an unsafe path segment.")

    if s3_client is None:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3-compatible off-site backups.") from exc
        s3_client = boto3.client(
            "s3",
            region_name=region.strip(),
            endpoint_url=endpoint_url or None,
        )

    digest = _sha256(path)
    key = "/".join(part for part in (clean_prefix, path.name) if part)
    extra_args = {
        "ContentType": "application/octet-stream",
        "Metadata": {"sha256": digest},
        "ServerSideEncryption": "aws:kms" if kms_key_id else "AES256",
    }
    if kms_key_id:
        extra_args["SSEKMSKeyId"] = kms_key_id
    s3_client.upload_file(str(path), bucket, key, ExtraArgs=extra_args)
    return key


def upload_backup_from_environment(backup_path: str | Path) -> str | None:
    """Export when OFFSITE_BACKUP_BUCKET is configured; otherwise do nothing."""
    bucket = os.getenv("OFFSITE_BACKUP_BUCKET", "").strip()
    if not bucket:
        return None
    return upload_backup(
        backup_path,
        bucket=bucket,
        region=os.getenv("OFFSITE_BACKUP_REGION", os.getenv("AWS_REGION", "us-east-1")),
        prefix=os.getenv("OFFSITE_BACKUP_PREFIX", "peak-adventure-backups"),
        endpoint_url=os.getenv("OFFSITE_BACKUP_ENDPOINT_URL") or None,
        kms_key_id=os.getenv("OFFSITE_BACKUP_KMS_KEY_ID") or None,
    )



def download_backup(
    *,
    bucket: str,
    key: str,
    destination: str | Path,
    region: str = "us-east-1",
    endpoint_url: str | None = None,
    s3_client=None,
) -> Path:
    """Download one S3 backup only after verifying its stored SHA-256 metadata.

    The object is first written to a temporary file beside the destination.
    A missing checksum, empty object, or checksum mismatch leaves the
    destination untouched.
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        raise ValueError("OFFSITE_BACKUP_BUCKET is not a valid S3 bucket name.")
    if not isinstance(key, str) or not key.strip() or key.startswith("/"):
        raise ValueError("A valid off-site backup object key is required.")
    if not isinstance(region, str) or not region.strip():
        raise ValueError("OFFSITE_BACKUP_REGION must not be empty.")

    if s3_client is None:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3-compatible off-site backups.") from exc
        s3_client = boto3.client(
            "s3",
            region_name=region.strip(),
            endpoint_url=endpoint_url or None,
        )

    metadata = s3_client.head_object(Bucket=bucket, Key=key)
    expected = str((metadata.get("Metadata") or {}).get("sha256", "")).lower()
    content_length = metadata.get("ContentLength")
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Off-site backup is missing valid SHA-256 metadata.")
    if type(content_length) is not int or content_length <= 0:
        raise ValueError("Refusing to download an empty off-site backup.")

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".offsite-download-", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        s3_client.download_file(bucket, key, str(temporary))
        if not temporary.is_file() or temporary.stat().st_size != content_length:
            raise ValueError("Downloaded off-site backup size does not match object metadata.")
        if _sha256(temporary) != expected:
            raise ValueError("Downloaded off-site backup failed SHA-256 verification.")
        os.replace(temporary, target)
        return target
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
