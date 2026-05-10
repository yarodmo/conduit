"""
Conduit Backend — S3 Storage Helper
Wraps boto3 for plan uploads, tile storage, and signed URL generation.

Local dev fallback: files stored under /tmp/conduit-dev-storage when
S3_ACCESS_KEY is empty (avoids boto3 credential errors in unit tests).

Bliss Systems LLC — APEX Standard
"""

import io
import os
from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings

_s3_client = None


def _get_client():
    global _s3_client  # noqa: PLW0603
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT if settings.S3_ENDPOINT != "http://localhost:9000" else None,
            aws_access_key_id=settings.S3_ACCESS_KEY or None,
            aws_secret_access_key=settings.S3_SECRET_KEY or None,
            region_name="us-east-1",
            config=Config(signature_version="s3v4"),
        )
    return _s3_client


def _local_path(key: str) -> Path:
    """Dev fallback: resolve an S3 key to a local temp path."""
    base = Path("/tmp/conduit-dev-storage")
    p = (base / key).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _is_dev_mode() -> bool:
    return not settings.S3_ACCESS_KEY


def upload_fileobj(
    fileobj: BinaryIO,
    bucket: str,
    key: str,
    content_type: str = "application/octet-stream",
    extra_args: dict | None = None,
) -> str:
    """Upload a file-like object. Returns the S3 key."""
    if _is_dev_mode():
        data = fileobj.read()
        _local_path(key).write_bytes(data)
        return key

    args: dict = {"ContentType": content_type}
    if extra_args:
        args.update(extra_args)
    _get_client().upload_fileobj(fileobj, bucket, key, ExtraArgs=args)
    return key


def upload_bytes(
    data: bytes,
    bucket: str,
    key: str,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload raw bytes. Returns the S3 key."""
    return upload_fileobj(io.BytesIO(data), bucket, key, content_type)


def download_bytes(bucket: str, key: str) -> bytes:
    """Download an object as bytes."""
    if _is_dev_mode():
        p = _local_path(key)
        if p.exists():
            return p.read_bytes()
        raise FileNotFoundError(f"Dev storage: {key} not found")

    buf = io.BytesIO()
    _get_client().download_fileobj(bucket, key, buf)
    return buf.getvalue()


def get_presigned_url(bucket: str, key: str, expires_in: int = 3600) -> str:
    """Generate a pre-signed GET URL (1 hour default)."""
    if _is_dev_mode():
        return f"/dev-storage/{key}"

    return _get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def object_exists(bucket: str, key: str) -> bool:
    if _is_dev_mode():
        return _local_path(key).exists()
    try:
        _get_client().head_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False


def plan_s3_prefix(org_id: str, project_id: str, plan_id: str) -> str:
    return f"{org_id}/{project_id}/{plan_id}"


def plan_page_full_key(org_id: str, project_id: str, plan_id: str, page: int) -> str:
    return f"{plan_s3_prefix(org_id, project_id, plan_id)}/pages/{page}/full.png"


def plan_page_thumb_key(org_id: str, project_id: str, plan_id: str, page: int) -> str:
    return f"{plan_s3_prefix(org_id, project_id, plan_id)}/pages/{page}/thumb.jpg"


def plan_tile_key(plan_id: str, page: int, zoom: int, x: int, y: int) -> str:
    return f"tiles/{plan_id}/{page}/{zoom}/{x}/{y}.webp"


def plan_original_key(org_id: str, project_id: str, plan_id: str, ext: str) -> str:
    return f"{plan_s3_prefix(org_id, project_id, plan_id)}/original.{ext}"
