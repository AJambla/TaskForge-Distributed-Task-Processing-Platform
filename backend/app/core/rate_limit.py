"""Rate limiting dependency for FastAPI routes using Redis fixed-window counters."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Header, Request, status

from app.core.redis import increment_rate_limit_counter

logger = logging.getLogger(__name__)

RATE_LIMIT_WINDOW_SECONDS = 60


def make_rate_limiter(limit: int):
    """Factory that creates a rate-limit dependency with a fixed limit."""
    async def _rate_limit(
        request: Request,
        api_key_header: Annotated[
            str | None, Header(alias="X-API-Key", lowercase=True)
        ] = None,
    ) -> None:
        # Skip rate limiting for OPTIONS (CORS preflight) requests
        if request.method == "OPTIONS":
            return

        if api_key_header:
            identifier = api_key_header
        elif request.headers.get("authorization", "").startswith("Bearer "):
            token = request.headers["authorization"][7:]
            identifier = f"auth:{token[:16]}"
        else:
            identifier = request.client.host if request.client else "unknown"

        key = f"ratelimit:{identifier}:{RATE_LIMIT_WINDOW_SECONDS}"
        count = await increment_rate_limit_counter(key, limit, RATE_LIMIT_WINDOW_SECONDS)

        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": f"Too many requests. Limit is {limit} per {RATE_LIMIT_WINDOW_SECONDS}s window.",
                        "field": None,
                    }
                },
            )
    return _rate_limit
