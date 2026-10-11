"""FastAPI dependency injection for authentication and authorization.

Implements dual-auth: JWT Bearer tokens (dashboard) and API keys (programmatic).
Per API.md: Both are passed as 'Authorization: Bearer <token>'; the API
distinguishes them by token format (JWTs are structurally distinct from
the 'tf_live_...' API key format).
"""
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, hash_api_key
from app.database import get_db
from app.models.api_key import APIKey
from app.models.user import User

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Extract and validate the current user from either:
    - A JWT access token (dashboard sessions)
    - An API key with tf_live_ prefix (programmatic access)

    Returns the authenticated User model instance.
    Raises HTTP 401 if credentials are missing or invalid.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHENTICATED", "message": "Authorization header required."}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Dispatch by token format
    if token.startswith("tf_live_"):
        return await _auth_via_api_key(token, db)
    else:
        return await _auth_via_jwt(token, db)


async def _auth_via_jwt(token: str, db: AsyncSession) -> User:
    """Validate a JWT access token and return the owning User."""
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid or expired access token."}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_type = payload.get("type")
    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Token is not an access token."}},
        )

    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Token missing subject."}},
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid subject in token."}},
        )

    redis_client = None
    try:
        from app.core.redis import get_redis
        redis_client = await get_redis()
        cached_raw = await redis_client.get(f"auth:user:{user_id}")
        if cached_raw:
            import json
            data = json.loads(cached_raw)
            return User(
                id=uuid.UUID(data["id"]),
                email=data["email"],
                password_hash=data.get("password_hash", ""),
                role=data.get("role", "user"),
            )
    except Exception:
        pass

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "User no longer exists."}},
        )

    if redis_client is not None:
        try:
            import json
            user_data = {
                "id": str(user.id),
                "email": user.email,
                "password_hash": user.password_hash,
                "role": user.role,
            }
            await redis_client.set(f"auth:user:{user.id}", json.dumps(user_data), ex=60)
        except Exception:
            pass

    return user


async def _auth_via_api_key(raw_key: str, db: AsyncSession) -> User:
    """Validate an API key and return the owning User. Updates last_used_at."""
    key_hash = hash_api_key(raw_key)

    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash)
    )
    api_key = result.scalar_one_or_none()

    if not api_key or not api_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_API_KEY", "message": "Invalid or revoked API key."}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Debounce last_used_at updates in Redis to at most once per 60s
    should_update = False
    try:
        from app.core.redis import get_redis
        redis_client = await get_redis()
        should_update = bool(await redis_client.set(f"apikey:last_used:{api_key.id}", "1", nx=True, ex=60))
    except Exception:
        should_update = (
            api_key.last_used_at is None
            or (datetime.now(timezone.utc) - api_key.last_used_at).total_seconds() > 60
        )

    if should_update:
        await db.execute(
            update(APIKey)
            .where(APIKey.id == api_key.id)
            .values(last_used_at=datetime.now(timezone.utc))
        )
        await db.commit()

    # Load the user (checking cache first)
    redis_client = None
    try:
        from app.core.redis import get_redis
        redis_client = await get_redis()
        cached_raw = await redis_client.get(f"auth:user:{api_key.user_id}")
        if cached_raw:
            import json
            data = json.loads(cached_raw)
            return User(
                id=uuid.UUID(data["id"]),
                email=data["email"],
                password_hash=data.get("password_hash", ""),
                role=data.get("role", "user"),
            )
    except Exception:
        pass

    result = await db.execute(select(User).where(User.id == api_key.user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "User not found."}},
        )

    if redis_client is not None:
        try:
            import json
            user_data = {
                "id": str(user.id),
                "email": user.email,
                "password_hash": user.password_hash,
                "role": user.role,
            }
            await redis_client.set(f"auth:user:{user.id}", json.dumps(user_data), ex=60)
        except Exception:
            pass

    return user


def require_admin(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """Dependency that additionally requires admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": "Admin role required."}},
        )
    return current_user


# Convenience type aliases for use in route signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
DBSession = Annotated[AsyncSession, Depends(get_db)]
