"""Exception handlers — produce the standard error envelope per API.md.

Every error response has the shape:
    {"error": {"code": "...", "message": "...", "field": "..."}}
"""
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def error_response(
    status_code: int,
    code: str,
    message: str,
    field: str | None = None,
) -> JSONResponse:
    """Build a JSON response matching the standard error envelope."""
    body = {
        "error": {
            "code": code,
            "message": message,
            "field": field,
        }
    }
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(body),
    )


async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Map Pydantic validation errors to a 400 with field-level detail.

    Extracts the first validation error and reports its field and message.
    """
    errors = exc.errors()
    if errors:
        first = errors[0]
        field = ".".join(str(part) for part in (first.get("loc") or ()))
        msg = first.get("msg", "Invalid request body.")
        return error_response(400, "VALIDATION_ERROR", msg, field or None)
    return error_response(400, "VALIDATION_ERROR", "Invalid request body.")


async def http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Map HTTPException to the standard envelope.

    Preserves the status code. If the detail is already a dict with an
    'error' key (as produced by auth dependencies), pass it through.
    """
    status_code = exc.status_code
    detail = exc.detail

    if isinstance(detail, dict) and "error" in detail:
        return JSONResponse(status_code=status_code, content=detail)

    code = _code_for_status(status_code)
    message = str(detail) if detail else _message_for_status(status_code)
    return error_response(status_code, code, message)


async def unhandled_exception_handler(
    _request: Request, _exc: Exception
) -> JSONResponse:
    """Last-resort handler — never leak internal details."""
    return error_response(
        500, "INTERNAL_ERROR", "An unexpected error occurred."
    )


def _code_for_status(status_code: int) -> str:
    if status_code == 400:
        return "VALIDATION_ERROR"
    if status_code == 401:
        return "UNAUTHENTICATED"
    if status_code == 403:
        return "FORBIDDEN"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 409:
        return "CONFLICT"
    if status_code == 429:
        return "RATE_LIMITED"
    return "HTTP_ERROR"


def _message_for_status(status_code: int) -> str:
    if status_code == 400:
        return "Bad request."
    if status_code == 401:
        return "Authentication required."
    if status_code == 403:
        return "Forbidden."
    if status_code == 404:
        return "Resource not found."
    if status_code == 409:
        return "Conflict."
    if status_code == 429:
        return "Too many requests."
    return "Request failed."


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI app."""
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
