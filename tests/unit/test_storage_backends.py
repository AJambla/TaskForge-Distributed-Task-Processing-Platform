"""Unit tests for pluggable storage backend and HMAC signed URLs (FEAT-01)."""
import time
from pathlib import Path
import pytest

from app.core.storage import (
    LocalStorageBackend,
    get_storage_backend,
    verify_download_signature,
)


def test_local_storage_save_and_verify(tmp_path):
    backend = LocalStorageBackend(base_dir=str(tmp_path), secret_key="test-secret-key-32-chars-long!")
    key = "tasks/test-task/output/image.png"
    data = b"fake-png-content"

    saved_key = backend.save(key, data, content_type="image/png")
    assert saved_key == key

    # File exists on disk
    file_path = tmp_path / "tasks" / "test-task" / "output" / "image.png"
    assert file_path.exists()
    assert file_path.read_bytes() == data


def test_local_storage_generate_signed_url_and_validate(tmp_path):
    secret = "test-secret-key-32-chars-long!"
    backend = LocalStorageBackend(base_dir=str(tmp_path), secret_key=secret)
    key = "tasks/123/artifacts/chart.png"
    filename = "chart.png"

    url = backend.generate_download_url(key, filename=filename, expires_in=60)
    assert "/api/v1/storage/download/tasks/123/artifacts/chart.png" in url
    assert "expires=" in url
    assert "signature=" in url

    # Parse query parameters from url
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    expires_at = int(params["expires"][0])
    sig = params["signature"][0]

    # Valid signature
    assert verify_download_signature(key, filename, expires_at, sig, secret_key=secret) is True

    # Tampered key or filename
    assert verify_download_signature("tampered/key.png", filename, expires_at, sig, secret_key=secret) is False
    assert verify_download_signature(key, "other.png", expires_at, sig, secret_key=secret) is False

    # Expired timestamp
    expired_ts = int(time.time()) - 10
    assert verify_download_signature(key, filename, expired_ts, sig, secret_key=secret) is False


def test_local_storage_path_traversal_prevention(tmp_path):
    backend = LocalStorageBackend(base_dir=str(tmp_path), secret_key="secret")
    with pytest.raises(ValueError, match="Path traversal detected"):
        backend.save("../../etc/passwd", b"malicious", content_type="text/plain")

    with pytest.raises(ValueError, match="Path traversal detected"):
        backend.resolve_path("../../etc/passwd")
