"""Rate limiting dependency for FastAPI routes using Redis fixed-window counters."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Header, HTTPException, status
from starlette.requests import Request as StarletteRequest

from app.core.redis import increment_rate_limit_counter

logger = logging.getLogger(__name__)

RATE_LIMIT_WINDOW_SECONDS = 60


class RateLimiter:
    """Dependency that enforces a fixed-window rate limit via Redis.

    For authenticated requests, the limit key is based on the API key or
    JWT-subject. For unauthenticated requests (e.g. auth routes), the
    client IP is used.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit

    async def __call__(
        self,
        request: StarletteRequest,
        api_key_header: Annotated[
            str | None, Header(alias="X-API-Key", lowercase=True)
        ] = None,
    ) -> None:
        if api_key_header:
            identifier = api_key_header
        elif request.headers.get("authorization", "").startswith("Bearer "):
            token = request.headers["authorization"][7:]
            identifier = f"auth:{token[:16]}"
        else:
            identifier = request.client.host if request.client else "unknown"

        key = f"ratelimit:{identifier}:{RATE_LIMIT_WINDOW_SECONDS}"
        count = await increment_rate_limit_counter(key, self.limit, RATE_LIMIT_WINDOW_SECONDS)

        if count > self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": f"Too many requests. Limit is {self.limit} per {RATE_LIMIT_WINDOW_SECONDS}s window.",
                        "field": None,
                    }
                },
            )
