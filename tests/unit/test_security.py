"""Unit tests for security utilities."""
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    hash_refresh_token,
    verify_password,
    validate_password_strength,
)


def test_password_hash_and_verify():
    password = "SecurePass1!"
    hashed = hash_password(password)
    assert verify_password(password, hashed)
    assert not verify_password("wrong_password", hashed)


def test_password_strength_validation():
    assert validate_password_strength("short") == ["Password must be at least 8 characters long."]
    assert validate_password_strength("nouppernum") == [
        "Password must contain at least one uppercase letter.",
        "Password must contain at least one digit.",
    ]
    assert validate_password_strength("NoLower1!") == [
        "Password must contain at least one lowercase letter."
    ]
    assert validate_password_strength("ProperPass1!") == []


def test_jwt_encode_decode():
    import uuid
    user_id = uuid.uuid4()
    token, expires = create_access_token(user_id, "admin")
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_jwt_invalid_token():
    from jose import JWTError
    with pytest.raises(JWTError):
        decode_access_token("invalid.token.here")


def test_api_key_generation():
    raw, key_hash, prefix = generate_api_key()
    assert raw.startswith("tf_live_")
    assert len(raw) == 12 + 64  # prefix + 32 bytes hex
    assert prefix == raw[:12]
    assert hash_api_key(raw) == key_hash


def test_refresh_token_hash():
    raw = "test_refresh_token_value"
    hashed = hash_refresh_token(raw)
    assert isinstance(hashed, str)
    assert len(hashed) == 64  # SHA-256 hex digest


def test_create_refresh_token():
    import uuid
    user_id = uuid.uuid4()
    raw, hashed, expires = create_refresh_token(user_id)
    assert raw.startswith("_") or len(raw) > 20
    assert hashed == hash_refresh_token(raw)
    assert expires > __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
