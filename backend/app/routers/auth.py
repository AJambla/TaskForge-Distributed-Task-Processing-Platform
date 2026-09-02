"""Auth router — register, login, refresh, logout.

Per API.md:
- POST /api/v1/auth/register — 201 with {id, email}
- POST /api/v1/auth/login — 200 {access_token, refresh_token, expires_in}
- POST /api/v1/auth/refresh — 200 {access_token, expires_in}
- POST /api/v1/auth/logout — 204, revokes ALL of the user's refresh tokens
"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.core.deps import CurrentUser, DBSession
from app.core.rate_limit import make_rate_limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
)

router = APIRouter()


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    db: DBSession,
    rate_limit: Annotated[None, Depends(make_rate_limiter(get_settings().rate_limit_auth_per_minute))],
) -> RegisterResponse:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "EMAIL_ALREADY_REGISTERED",
                    "message": "An account with this email already exists.",
                    "field": "email",
                }
            },
        )

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "EMAIL_ALREADY_REGISTERED",
                    "message": "An account with this email already exists.",
                    "field": "email",
                }
            },
        )
    await db.refresh(user)
    return RegisterResponse(id=user.id, email=user.email)


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: DBSession,
    rate_limit: Annotated[None, Depends(make_rate_limiter(get_settings().rate_limit_auth_per_minute))],
) -> LoginResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_CREDENTIALS",
                    "message": "Invalid email or password.",
                    "field": None,
                }
            },
        )

    access_token, access_expires = create_access_token(user.id, user.role)
    raw_refresh, refresh_hash, refresh_expires = create_refresh_token(user.id)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=refresh_expires,
        )
    )
    await db.commit()

    expires_in = int(
        (access_expires - datetime.now(timezone.utc)).total_seconds()
    )
    return LoginResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=expires_in,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    body: RefreshRequest,
    db: DBSession,
) -> RefreshResponse:
    token_hash = hash_refresh_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    refresh_record = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if (
        not refresh_record
        or refresh_record.revoked
        or refresh_record.expires_at <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_REFRESH_TOKEN",
                    "message": "Invalid, revoked, or expired refresh token.",
                    "field": None,
                }
            },
        )

    user_result = await db.execute(
        select(User).where(User.id == refresh_record.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "User no longer exists.",
                    "field": None,
                }
            },
        )

    access_token, access_expires = create_access_token(user.id, user.role)
    raw_refresh, refresh_hash, refresh_expires = create_refresh_token(user.id)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=refresh_expires,
        )
    )
    await db.commit()
    refresh_record.revoked = True
    await db.commit()

    expires_in = int(
        (access_expires - datetime.now(timezone.utc)).total_seconds()
    )
    return RefreshResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=expires_in,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: CurrentUser,
    db: DBSession,
) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == current_user.id)
        .values(revoked=True)
    )
    await db.commit()
