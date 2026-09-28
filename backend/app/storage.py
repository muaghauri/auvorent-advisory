import os
import boto3
from botocore.exceptions import ClientError


def r2_enabled() -> bool:
    required = (
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_ENDPOINT_URL",
        "R2_BUCKET",
    )
    return all(os.getenv(name) for name in required)


def _client():
    if not r2_enabled():
        raise RuntimeError("R2 storage is not configured")

    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def bucket_name() -> str:
    return os.environ["R2_BUCKET"]


def put_bytes(key: str, data: bytes, content_type: str | None = None) -> None:
    args = {
        "Bucket": bucket_name(),
        "Key": key,
        "Body": data,
    }

    if content_type:
        args["ContentType"] = content_type

    _client().put_object(**args)


def get_bytes(key: str) -> bytes:
    response = _client().get_object(
        Bucket=bucket_name(),
        Key=key,
    )
    return response["Body"].read()


def delete_object(key: str) -> None:
    _client().delete_object(
        Bucket=bucket_name(),
        Key=key,
    )


def object_exists(key: str) -> bool:
    try:
        _client().head_object(
            Bucket=bucket_name(),
            Key=key,
        )
        return True
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise
