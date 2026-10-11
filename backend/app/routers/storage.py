"""Storage download routing for local file streaming with HMAC validation (FEAT-01)."""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.core.storage import get_storage_backend, verify_download_signature

logger = logging.getLogger("routers.storage")
router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/download/{storage_key:path}", summary="Stream signed local artifact")
async def download_local_artifact(
    storage_key: str,
    filename: str = Query(..., description="Target download filename"),
    expires: int = Query(..., description="UNIX expiration timestamp"),
    signature: str = Query(..., description="HMAC-SHA256 signature"),
):
    """Validate signature and stream file directly."""
    clean_key = unquote(storage_key).lstrip("/\\")

    if not verify_download_signature(clean_key, filename, expires, signature):
        logger.warning("Rejected invalid or expired signature for key: %s", clean_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "INVALID_DOWNLOAD_SIGNATURE",
                    "message": "Download URL is invalid or has expired.",
                    "field": None,
                }
            },
        )

    storage = get_storage_backend()
    try:
        file_path: Path = storage.resolve_path(clean_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_STORAGE_PATH", "message": str(exc), "field": None}},
        )

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "FILE_NOT_FOUND", "message": "Artifact file not found.", "field": None}},
        )

    # Determine media type from file extension
    ext = file_path.suffix.lstrip(".").lower()
    media_type = f"image/{ext}" if ext in ("png", "jpeg", "jpg", "webp", "gif") else "application/octet-stream"

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )
