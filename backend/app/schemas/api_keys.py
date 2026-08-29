"""Pydantic schemas for API key endpoints — per API.md."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateAPIKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Human-readable label for this key.")


class CreateAPIKeyResponse(BaseModel):
    """Returned once on creation — includes the full raw key (never returned again)."""
    id: uuid.UUID
    name: str
    key: str  # Full 'tf_live_...' key — shown ONCE ONLY
    key_prefix: str
    created_at: datetime

    model_config = {"from_attributes": True}


class APIKeyListItem(BaseModel):
    """Item in GET /api-keys — no full key, only prefix for identification."""
    id: uuid.UUID
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    model_config = {"from_attributes": True}
