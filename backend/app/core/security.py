"""Core security utilities: password hashing, JWT, API key generation.

Per SECURITY.md:
- Passwords hashed with bcrypt (passlib)
- API keys stored as SHA-256 hash only; raw key shown once at creation
- Short-lived access tokens (~15 min) + revocable refresh tokens (~30 days)
- Refresh tokens stored hashed in Postgres
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

# bcrypt password hashing — per SECURITY.md
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# API key prefix per API.md
API_KEY_PREFIX = "tf_live_"
API_KEY_BYTES = 32  # 32 bytes = 64 hex chars of entropy


# ─── Password helpers ────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ─── API Key helpers ─────────────────────────────────────────────────────────

def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        (raw_key, key_hash, key_prefix)
        - raw_key: the full key shown to the user ONCE
        - key_hash: SHA-256 hash stored in DB
        - key_prefix: first 12 chars (prefix + 4 random chars) for display
    """
    random_bytes = secrets.token_hex(API_KEY_BYTES)
    raw_key = f"{API_KEY_PREFIX}{random_bytes}"
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:12]  # e.g. "tf_live_a1b2"
    return raw_key, key_hash, key_prefix


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hash of a raw API key for storage."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ─── JWT helpers ─────────────────────────────────────────────────────────────

def create_access_token(user_id: uuid.UUID, role: str) -> tuple[str, datetime]:
    """Create a short-lived JWT access token.

    Returns (token_string, expiry_datetime).
    """
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "exp": expires,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return token, expires


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str, datetime]:
    """Create a refresh token.

    Returns (raw_token, hashed_token, expiry_datetime).
    The raw token is returned to the client; only the hash is stored server-side.
    """
    raw_token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )
    hashed = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, hashed, expires


def hash_refresh_token(raw_token: str) -> str:
    """Hash a refresh token for storage/lookup."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT access token.

    Raises jose.JWTError on invalid/expired tokens.
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )


def validate_password_strength(password: str) -> list[str]:
    """Return a list of validation error messages; empty list = valid."""
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    if not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter.")
    if not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter.")
    if not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one digit.")
    return errors
