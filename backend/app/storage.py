from __future__ import annotations

import os
import re
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


_KEY_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,240}$")
_BUCKET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,62}$")
MAX_OBJECT_BYTES = 12 * 1024 * 1024


def r2_enabled() -> bool:
    required = (
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_ENDPOINT_URL",
        "R2_BUCKET",
    )
    return all(os.getenv(name) for name in required)


def _safe_key(key: str) -> str:
    if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
        raise ValueError("Invalid object key")
    if key.startswith(("/", ".")) or ".." in key.split("/") or "//" in key:
        raise ValueError("Invalid object key")
    return key


def _safe_endpoint(raw: str) -> str:
    endpoint = (raw or "").strip().rstrip("/")
    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise RuntimeError("R2 endpoint must be a clean HTTPS origin")
    return endpoint


def _client():
    if not r2_enabled():
        raise RuntimeError("R2 storage is not configured")

    endpoint = _safe_endpoint(os.environ["R2_ENDPOINT_URL"])

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(
            connect_timeout=5,
            read_timeout=15,
            retries={"max_attempts": 3, "mode": "standard"},
            signature_version="s3v4",
        ),
    )


def bucket_name() -> str:
    bucket = os.environ["R2_BUCKET"].strip()
    if not _BUCKET_RE.fullmatch(bucket):
        raise RuntimeError("Invalid R2 bucket configuration")
    return bucket


def put_bytes(key: str, data: bytes, content_type: str | None = None) -> None:
    key = _safe_key(key)
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("Object data must be bytes")
    if len(data) > MAX_OBJECT_BYTES:
        raise ValueError("Object exceeds the permitted storage size")
    if content_type is not None:
        content_type = content_type.strip()
        if not content_type or len(content_type) > 120 or any(ord(c) < 32 for c in content_type):
            raise ValueError("Invalid object content type")

    args = {
        "Bucket": bucket_name(),
        "Key": key,
        "Body": data,
        "CacheControl": "public, max-age=31536000, immutable",
    }

    if content_type:
        args["ContentType"] = content_type

    _client().put_object(**args)


def get_bytes(key: str) -> bytes:
    response = _client().get_object(
        Bucket=bucket_name(),
        Key=_safe_key(key),
    )
    declared = response.get("ContentLength")
    if isinstance(declared, int) and declared > MAX_OBJECT_BYTES:
        try:
            response["Body"].close()
        finally:
            raise ValueError("Stored object exceeds the permitted size")

    body = response["Body"]
    try:
        data = body.read(MAX_OBJECT_BYTES + 1)
    finally:
        body.close()
    if len(data) > MAX_OBJECT_BYTES:
        raise ValueError("Stored object exceeds the permitted size")
    return data


def delete_object(key: str) -> None:
    _client().delete_object(
        Bucket=bucket_name(),
        Key=_safe_key(key),
    )


def object_exists(key: str) -> bool:
    try:
        _client().head_object(
            Bucket=bucket_name(),
            Key=_safe_key(key),
        )
        return True
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise
