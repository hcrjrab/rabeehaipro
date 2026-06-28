"""HTTP middlewares.

Currently provides:
- ``RateLimitMiddleware`` — simple in-memory sliding-window rate limiter.
- ``RequestTimingMiddleware`` — logs request duration for every HTTP call.
- ``CorrelationIdMiddleware`` — injects ``X-Request-ID`` headers and populates
  the structured logging context with ``request_id``.

No external dependencies are required. The rate limiter uses a
per-process dictionary; for multi-worker production deployments, replace
the backing store with Redis.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..config.logging import bind_context, clear_context

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RATE_LIMIT_DEFAULT: int = 60  # requests per window
RATE_LIMIT_WINDOW_SECONDS: int = 60  # sliding window size
RATE_LIMIT_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/healthz",
    "/readyz",
    "/info",
    "/auth/login",
    "/auth/refresh",
    "/docs",
    "/openapi.json",
)

# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

_window: dict[str, list[float]] = {}
"""Maps client IP → list of request timestamps within the current window."""


def _clean_window(now: float, window_seconds: int) -> None:
    """Drop entries whose window has expired."""
    cutoff = now - window_seconds
    expired = [k for k, v in _window.items() if v and v[-1] < cutoff]
    for k in expired:
        del _window[k]


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter.

    Tracks request frequency by client IP. Returns ``429 Too Many Requests``
    when the limit is exceeded. Exempts health, auth, and docs endpoints.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_requests: int = RATE_LIMIT_DEFAULT,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
        exempt_prefixes: tuple[str, ...] = RATE_LIMIT_EXEMPT_PREFIXES,
    ) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.exempt_prefixes = exempt_prefixes

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Exempt certain paths from rate limiting
        path = request.url.path
        if any(path.startswith(prefix) for prefix in self.exempt_prefixes):
            return await call_next(request)

        client_ip = self._client_ip(request)
        now = time.time()

        # Prune stale entries periodically
        _clean_window(now, self.window_seconds)

        # Get or create the timestamp list for this IP
        timestamps = _window.setdefault(client_ip, [])
        cutoff = now - self.window_seconds

        # Keep only timestamps within the current window
        timestamps[:] = [t for t in timestamps if t > cutoff]

        # Check limit
        if len(timestamps) >= self.max_requests:
            _log.warning("Rate limit exceeded for %s (%d requests)", client_ip, len(timestamps))
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
            )

        # Record this request
        timestamps.append(now)

        return await call_next(request)

    @staticmethod
    def _client_ip(request: Request) -> str:
        """Extract the client IP from headers or the direct connection."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        client_host = request.client.host if request.client else "unknown"
        return str(client_host)


# ---------------------------------------------------------------------------
# Request timing
# ---------------------------------------------------------------------------


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Logs the duration of every HTTP request.

    Emits a DEBUG line for sub-second requests and a WARNING for requests
    that take longer than 1 s to help identify slow endpoints.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.monotonic()
        method = request.method
        path = request.url.path

        _log.debug("Request started: %s %s", method, path)
        response = None
        try:
            response = await call_next(request)
            return response
        except BaseException:
            _log.error(
                "Request failed: %s %s (after %.3fs)", method, path, time.monotonic() - start
            )
            raise
        finally:
            duration = time.monotonic() - start
            status = getattr(response, "status_code", 500)
            _log.log(
                logging.DEBUG if duration < 1 else logging.WARNING,
                "Request completed: %s %s -> %s in %.3fs",
                method,
                path,
                status,
                duration,
            )


# ---------------------------------------------------------------------------
# Correlation ID
# ---------------------------------------------------------------------------


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Injects a ``X-Request-ID`` header into every response.

    Reads an existing ``X-Request-ID`` from the incoming request (preserving
    upstream trace ids behind a reverse proxy) or generates a new UUID.
    The value is also pushed into the structured logging context so every
    log line during the request carries the correlation id, then cleared
    when the request completes.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        bind_context(request_id=correlation_id)

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = correlation_id
            return response
        except BaseException:
            raise
        finally:
            clear_context()


# ---------------------------------------------------------------------------
# App helper
# ---------------------------------------------------------------------------


def add_rate_limiting(app: FastAPI) -> None:
    """Convenience helper to attach the rate limiter to an existing app."""
    app.add_middleware(RateLimitMiddleware)
    _log.info(
        "Rate-limit middleware attached (max %d/%ds)", RATE_LIMIT_DEFAULT, RATE_LIMIT_WINDOW_SECONDS
    )
