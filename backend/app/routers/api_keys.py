"""API keys router — create, list, revoke.

Per API.md:
- POST /api/v1/api-keys — 201, returns the full raw key ONCE
- GET /api/v1/api-keys — 200, never returns the full key
- DELETE /api/v1/api-keys/{key_id} — 204, soft-delete (revoke)
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DBSession
from app.core.security import generate_api_key
from app.models.api_key import APIKey
from app.schemas.api_keys import (
    APIKeyListItem,
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
)

router = APIRouter()


@router.post(
    "",
    response_model=CreateAPIKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    body: CreateAPIKeyRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> CreateAPIKeyResponse:
    raw_key, key_hash, key_prefix = generate_api_key()

    api_key = APIKey(
        user_id=current_user.id,
        name=body.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return CreateAPIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        key_prefix=api_key.key_prefix,
        created_at=api_key.created_at,
    )


@router.get("", response_model=list[APIKeyListItem])
async def list_api_keys(
    current_user: CurrentUser,
    db: DBSession,
) -> list[APIKeyListItem]:
    result = await db.execute(
        select(APIKey)
        .where(APIKey.user_id == current_user.id)
        .order_by(APIKey.created_at.desc())
    )
    keys = result.scalars().all()
    return [APIKeyListItem.model_validate(key) for key in keys]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
) -> None:
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == key_id,
            APIKey.user_id == current_user.id,
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "API_KEY_NOT_FOUND",
                    "message": "API key not found.",
                    "field": None,
                }
            },
        )

    api_key.revoked_at = datetime.now(timezone.utc)
    await db.commit()
