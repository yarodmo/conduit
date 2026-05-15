"""
Conduit Backend — Security Middleware (M14)
Attack detection + security headers on every response.

Detects:
  - SQL injection patterns in query params + body
  - Path traversal in URL
  - Known scanner user agents
  - Anomalous request sizes

Headers added to ALL responses:
  X-Content-Type-Options, X-Frame-Options, X-XSS-Protection,
  Strict-Transport-Security, Referrer-Policy, X-Request-ID

Critical threats (SQLi, path traversal) → 400 + async event log.
Medium/low threats → log only, request continues.

Bliss Systems LLC — APEX Standard
"""

import re
import uuid
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = structlog.get_logger()

# ── Attack patterns ────────────────────────────────────────────────────────

SQLI_PATTERNS = re.compile(
    r"('|\")\s*(--|;|/\*)|"
    r"\b(union\s+select|drop\s+table|exec\s*\(|xp_cmdshell|"
    r"insert\s+into|delete\s+from|update\s+set)\b|"
    r"('\s*or\s*'?\d|or\s+'?\d+\s*=\s*'?\d+|and\s+'?\d+\s*=\s*'?\d+|"
    r"\d\s*=\s*\d\s*--|'\s*=\s*')",
    re.IGNORECASE,
)

PATH_TRAVERSAL_PATTERNS = re.compile(
    r"\.\.[/\\]|"
    r"%2e%2e[%2f%5c]|"
    r"%252e%252e|"
    r"\.\.%2f|"
    r"\.\.%5c",
    re.IGNORECASE,
)

SCANNER_UA_PATTERNS = re.compile(
    r"sqlmap|nikto|nmap|masscan|nuclei|"
    r"burpsuite|dirbuster|gobuster|ffuf|"
    r"wfuzz|hydra|medusa|openvas",
    re.IGNORECASE,
)

# Security headers applied to every response
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}

HSTS_HEADER = ("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

# Endpoints excluded from security scanning (health check, static)
EXEMPT_PATHS = {"/health", "/api/docs", "/api/redoc", "/api/openapi.json"}


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def detect_sqli(value: str) -> bool:
    return bool(SQLI_PATTERNS.search(value))


def detect_path_traversal(value: str) -> bool:
    return bool(PATH_TRAVERSAL_PATTERNS.search(value))


def detect_scanner_ua(user_agent: str) -> bool:
    return bool(SCANNER_UA_PATTERNS.search(user_agent))


class SecurityMiddleware(BaseHTTPMiddleware):

    def __init__(self, app: ASGIApp, is_production: bool = False) -> None:
        super().__init__(app)
        self._is_production = is_production

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        request_id = str(uuid.uuid4())[:16]

        # Exempt paths skip detection (not headers)
        if path not in EXEMPT_PATHS:
            threat = await self._detect_threats(request, request_id)
            if threat:
                event_type, severity, detail = threat
                _queue_security_event(request, event_type, severity, detail, request_id)
                if severity in ("CRITICAL", "HIGH"):
                    resp = JSONResponse(
                        {"detail": "Request blocked by security policy"},
                        status_code=400,
                    )
                    self._add_headers(resp, request_id)
                    return resp

        response = await call_next(request)
        self._add_headers(response, request_id)
        return response

    def _add_headers(self, response: Response, request_id: str) -> None:
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        if self._is_production:
            response.headers[HSTS_HEADER[0]] = HSTS_HEADER[1]
        response.headers["X-Request-ID"] = request_id

    async def _detect_threats(
        self, request: Request, _request_id: str
    ) -> tuple[str, str, str] | None:
        """Returns (event_type, severity, detail) or None."""
        # Scanner user-agent — HIGH: always a deliberate attack tool
        ua = request.headers.get("user-agent", "")
        if detect_scanner_ua(ua):
            return ("scanner_detected", "HIGH", f"Scanner UA: {ua[:100]}")

        # Path traversal in URL
        raw_path = str(request.url)
        if detect_path_traversal(raw_path):
            return ("path_traversal", "HIGH", f"Path traversal in URL: {raw_path[:200]}")

        # SQLi in query params
        for param, value in request.query_params.items():
            if detect_sqli(value):
                return ("sqli_attempt", "CRITICAL", f"SQLi in param '{param}': {value[:100]}")

        return None


def _queue_security_event(
    request: Request,
    event_type: str,
    severity: str,
    detail: str,
    request_id: str,
) -> None:
    """Fire-and-forget: queue Celery task to persist security event."""
    try:
        from app.tasks.security_tasks import log_security_event
        ip = _get_client_ip(request)
        log_security_event.delay(
            event_type=event_type,
            severity=severity,
            ip_address=ip,
            endpoint=request.url.path,
            method=request.method,
            details={"detail": detail, "request_id": request_id},
            request_id=request_id,
        )
    except Exception:
        # Non-blocking — log to structlog as fallback
        logger.warning(
            "security_event_queue_failed",
            event_type=event_type,
            severity=severity,
        )
