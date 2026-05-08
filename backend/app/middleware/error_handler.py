"""
Conduit Backend — Unified Error Handler
v11: "Errores: {error: string, code: string, details: object} siempre"

All domain exceptions map to consistent HTTP error responses.
"""

import traceback
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.responses import JSONResponse

logger = structlog.get_logger()


# ══════════════════════════════════════
# DOMAIN EXCEPTIONS
# ══════════════════════════════════════

class ConduitError(Exception):
    """Base exception for all Conduit domain errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class AuthenticationError(ConduitError):
    """Authentication failures."""

    def __init__(self, message: str = "Authentication failed", code: str = "AUTH_FAILED"):
        super().__init__(message, code, status.HTTP_401_UNAUTHORIZED)


class AuthorizationError(ConduitError):
    """Authorization / permission failures."""

    def __init__(self, message: str = "Permission denied", code: str = "FORBIDDEN"):
        super().__init__(message, code, status.HTTP_403_FORBIDDEN)


class NotFoundError(ConduitError):
    """Resource not found."""

    def __init__(self, resource: str = "Resource", code: str = "NOT_FOUND"):
        super().__init__(f"{resource} not found", code, status.HTTP_404_NOT_FOUND)


class ConflictError(ConduitError):
    """Resource conflict (e.g., duplicate email)."""

    def __init__(self, message: str = "Resource conflict", code: str = "CONFLICT"):
        super().__init__(message, code, status.HTTP_409_CONFLICT)


class RateLimitError(ConduitError):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int = 0,
    ):
        super().__init__(
            message,
            "RATE_LIMITED",
            status.HTTP_429_TOO_MANY_REQUESTS,
            {"retry_after_seconds": retry_after},
        )


class ValidationError(ConduitError):
    """Business logic validation failure."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, "VALIDATION_ERROR", status.HTTP_422_UNPROCESSABLE_ENTITY, details)


class AccountLockedError(ConduitError):
    """Account locked due to failed login attempts."""

    def __init__(self, retry_after: int = 0):
        super().__init__(
            "Account locked due to too many failed attempts",
            "ACCOUNT_LOCKED",
            status.HTTP_423_LOCKED,
            {"retry_after_seconds": retry_after},
        )


# ══════════════════════════════════════
# GLOBAL EXCEPTION HANDLERS
# ══════════════════════════════════════

def register_error_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI app."""

    @app.exception_handler(ConduitError)
    async def conduit_error_handler(request: Request, exc: ConduitError) -> JSONResponse:
        """Handle all ConduitError subclasses."""
        logger.warning(
            "domain_error",
            code=exc.code,
            message=exc.message,
            path=request.url.path,
            method=request.method,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError,
    ) -> JSONResponse:
        """Handle Pydantic validation errors with consistent format."""
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            })

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Validation failed",
                "code": "VALIDATION_ERROR",
                "details": {"errors": errors},
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """Normalize FastAPI HTTPExceptions to APEX standard format."""
        detail = exc.detail
        if isinstance(detail, dict):
            error_msg = detail.get("error", str(detail))
            code = detail.get("code", "HTTP_ERROR")
            details = detail.get("details", {})
        else:
            error_msg = str(detail)
            code = "HTTP_ERROR"
            details = {}

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": error_msg,
                "code": code,
                "details": details,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Catch-all for unhandled exceptions.
        LAW: Never leak stack traces to client in production.
        """
        logger.error(
            "unhandled_error",
            error=str(exc),
            traceback=traceback.format_exc(),
            path=request.url.path,
            method=request.method,
        )

        from app.core.config import settings

        detail = str(exc) if settings.APP_DEBUG else "An internal error occurred"

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": detail,
                "code": "INTERNAL_ERROR",
                "details": {},
            },
        )
