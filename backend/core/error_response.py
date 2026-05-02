"""
Standardized API error response model (Item 68).

All API errors use this schema — never leak stack traces or internal details.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class APIError(BaseModel):
    """Canonical error response. Never include stack traces or internal paths."""
    error: str           # Human-readable description
    code: str            # Machine-readable error code
    field: Optional[str] = None       # Which field caused the error (validation errors)
    request_id: Optional[str] = None  # Trace ID from request headers


def error_response(
    status_code: int,
    code: str,
    message: str,
    field: Optional[str] = None,
    request_id: Optional[str] = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=APIError(
            error=message,
            code=code,
            field=field,
            request_id=request_id,
        ).model_dump(exclude_none=True),
    )


def register_exception_handlers(app) -> None:
    """Register global exception handlers on the FastAPI app."""
    import logging
    logger = logging.getLogger(__name__)

    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        request_id = getattr(request.state, "request_id", None)
        detail = exc.detail
        if isinstance(detail, dict):
            code = detail.get("code", "error")
            message = detail.get("error", str(detail))
        else:
            code = "error"
            message = str(detail)
        return error_response(exc.status_code, code, message, request_id=request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", None)
        errors = exc.errors()
        first = errors[0] if errors else {}
        field = ".".join(str(loc) for loc in first.get("loc", []) if loc != "body")
        message = first.get("msg", "Validation error")
        return error_response(422, "validation_error", message, field=field, request_id=request_id)

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", None)
        logger.error("Unhandled exception", exc_info=True, extra={"request_id": request_id})
        return error_response(
            500,
            "internal_error",
            "An unexpected error occurred. Please try again or contact support.",
            request_id=request_id,
        )
