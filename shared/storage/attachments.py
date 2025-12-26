"""
S3-compatible storage helpers for workflow/run attachments.

Designed to work with Cloudflare R2 but functions with any S3 API
as long as the credentials and endpoint are provided via environment.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from pydantic_settings import BaseSettings


class AttachmentStorageError(RuntimeError):
    """Raised when attachment storage is misconfigured or fails."""


class AttachmentStorageConfig(BaseSettings):
    """Environment-driven configuration for attachment storage."""

    ATTACHMENTS_BUCKET: str = ""
    ATTACHMENTS_ENDPOINT_URL: str = ""
    ATTACHMENTS_REGION: str = "auto"
    ATTACHMENTS_ACCESS_KEY_ID: str = ""
    ATTACHMENTS_SECRET_ACCESS_KEY: str = ""
    ATTACHMENTS_PRESIGN_TTL_SECONDS: int = 900

    class Config:
        env_file = ".env"
        extra = "ignore"


class _AttachmentStorage:
    """Thin wrapper around boto3 client with defensive defaults."""

    def __init__(self, config: AttachmentStorageConfig) -> None:
        if not config.ATTACHMENTS_BUCKET:
            raise AttachmentStorageError("attachment bucket is not configured")
        if not (config.ATTACHMENTS_ACCESS_KEY_ID and config.ATTACHMENTS_SECRET_ACCESS_KEY):
            raise AttachmentStorageError("attachment storage credentials are not configured")
        if not config.ATTACHMENTS_ENDPOINT_URL:
            raise AttachmentStorageError("attachment storage endpoint is not configured")

        self._config = config
        session = boto3.session.Session()
        self._client = session.client(
            "s3",
            endpoint_url=config.ATTACHMENTS_ENDPOINT_URL,
            region_name=config.ATTACHMENTS_REGION,
            aws_access_key_id=config.ATTACHMENTS_ACCESS_KEY_ID,
            aws_secret_access_key=config.ATTACHMENTS_SECRET_ACCESS_KEY,
            config=BotoConfig(signature_version="s3v4"),
        )

    @property
    def bucket(self) -> str:
        return self._config.ATTACHMENTS_BUCKET

    def generate_presigned_put(
        self,
        key: str,
        *,
        content_type: Optional[str] = None,
        expires_in: Optional[int] = None,
    ) -> str:
        params: Dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if content_type:
            params["ContentType"] = content_type
        return self._client.generate_presigned_url(
            "put_object",
            Params=params,
            ExpiresIn=expires_in or self._config.ATTACHMENTS_PRESIGN_TTL_SECONDS,
        )

    def generate_presigned_get(self, key: str, *, expires_in: Optional[int] = None) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in or self._config.ATTACHMENTS_PRESIGN_TTL_SECONDS,
        )

    def head_object(self, key: str) -> Dict[str, Any]:
        return self._client.head_object(Bucket=self.bucket, Key=key)

    def list_objects(
        self,
        *,
        prefix: str,
        delimiter: Optional[str] = None,
        max_keys: Optional[int] = None,
        continuation_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"Bucket": self.bucket, "Prefix": prefix}
        if delimiter:
            params["Delimiter"] = delimiter
        if max_keys:
            params["MaxKeys"] = max_keys
        if continuation_token:
            params["ContinuationToken"] = continuation_token
        return self._client.list_objects_v2(**params)

    def copy_object(self, source_key: str, destination_key: str) -> None:
        self._client.copy_object(
            Bucket=self.bucket,
            Key=destination_key,
            CopySource={"Bucket": self.bucket, "Key": source_key},
        )

    def delete_object(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:  # pragma: no cover - defensive logging
            code = exc.response.get("Error", {}).get("Code")
            if code not in {"NoSuchBucket", "NoSuchKey"}:
                raise

    def upload_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        extra: Dict[str, Any] = {}
        if content_type:
            extra["ContentType"] = content_type
        if metadata:
            extra["Metadata"] = metadata
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)


@lru_cache(maxsize=1)
def get_attachment_storage() -> _AttachmentStorage:
    """Return singleton attachment storage client."""
    config = AttachmentStorageConfig()
    return _AttachmentStorage(config)