"""Storage abstraction and backends (Local HMAC & S3 Presigned) for TaskForge (FEAT-01)."""
from __future__ import annotations

import hmac
import hashlib
import logging
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import urlencode

from app.config import get_settings

logger = logging.getLogger("core.storage")


def generate_hmac_signature(key: str, filename: str, expires_at: int, secret_key: str) -> str:
    """Generate SHA256 HMAC signature for local download URL authorization."""
    msg = f"{key}:{filename}:{expires_at}".encode("utf-8")
    return hmac.new(secret_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_download_signature(
    key: str, filename: str, expires_at: int, signature: str, secret_key: str | None = None
) -> bool:
    """Validate signature and expiration timestamp for a download request."""
    if int(time.time()) > expires_at:
        return False
    secret = secret_key or get_settings().jwt_secret_key
    expected_sig = generate_hmac_signature(key, filename, expires_at, secret)
    return hmac.compare_digest(expected_sig, signature)


class StorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Persist binary data and return the storage key."""
        pass

    @abstractmethod
    def generate_download_url(self, key: str, filename: str, expires_in: int = 900) -> str:
        """Generate a temporary signed download URL."""
        pass

    @abstractmethod
    def resolve_path(self, key: str) -> Path:
        """Resolve a storage key to a local filesystem Path (local backend only)."""
        pass


class LocalStorageBackend(StorageBackend):
    def __init__(self, base_dir: str | None = None, secret_key: str | None = None):
        settings = get_settings()
        self.base_dir = Path(base_dir or settings.storage_local_dir).resolve()
        self.secret_key = secret_key or settings.jwt_secret_key
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _safe_resolve(self, key: str) -> Path:
        # Strip leading slashes to prevent root escapes
        clean_key = key.lstrip("/\\")
        target = (self.base_dir / clean_key).resolve()
        try:
            target.relative_to(self.base_dir)
        except ValueError as exc:
            raise ValueError(f"Path traversal detected for storage key: {key}") from exc
        return target

    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        target = self._safe_resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        logger.info("Saved %d bytes to local storage key '%s'", len(data), key)
        return key

    def generate_download_url(self, key: str, filename: str, expires_in: int = 900) -> str:
        expires_at = int(time.time()) + expires_in
        sig = generate_hmac_signature(key, filename, expires_at, self.secret_key)
        params = urlencode({"filename": filename, "expires": expires_at, "signature": sig})
        # Format as relative API path
        clean_key = key.lstrip("/")
        return f"/api/v1/storage/download/{clean_key}?{params}"

    def resolve_path(self, key: str) -> Path:
        return self._safe_resolve(key)


class S3StorageBackend(StorageBackend):
    def __init__(self):
        settings = get_settings()
        self.bucket = settings.s3_bucket_name
        self.endpoint_url = settings.s3_endpoint_url
        self.region = settings.s3_region
        self.access_key = settings.s3_access_key_id
        self.secret_key = settings.s3_secret_access_key

    def _get_client(self):
        import boto3
        kwargs = {"region_name": self.region}
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        if self.access_key and self.secret_key:
            kwargs["aws_access_key_id"] = self.access_key
            kwargs["aws_secret_access_key"] = self.secret_key
        return boto3.client("s3", **kwargs)

    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        s3 = self._get_client()
        s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    def generate_download_url(self, key: str, filename: str, expires_in: int = 900) -> str:
        s3 = self._get_client()
        return s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
            },
            ExpiresIn=expires_in,
        )

    def resolve_path(self, key: str) -> Path:
        raise NotImplementedError("Direct filesystem path resolution is unsupported for S3 storage.")


_STORAGE_INSTANCE: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Return configured singleton storage backend adapter."""
    global _STORAGE_INSTANCE
    if _STORAGE_INSTANCE is None:
        settings = get_settings()
        if settings.storage_backend == "s3":
            try:
                _STORAGE_INSTANCE = S3StorageBackend()
            except Exception as exc:
                logger.warning("Failed to initialize S3 backend (%s), falling back to LocalStorageBackend", exc)
                _STORAGE_INSTANCE = LocalStorageBackend()
        else:
            _STORAGE_INSTANCE = LocalStorageBackend()
    return _STORAGE_INSTANCE
