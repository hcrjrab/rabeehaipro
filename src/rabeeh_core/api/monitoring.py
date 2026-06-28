"""Monitoring, metrics, and optional OpenTelemetry instrumentation.

Usage
-----
Call ``setup_monitoring(app)`` inside the FastAPI application factory to
attach a ``/metrics`` endpoint (when ``prometheus_client`` is installed) and
a metrics-collection middleware.

If the optional ``opentelemetry-instrumentation-fastapi`` package is
available, distributed tracing is enabled alongside Prometheus metrics.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..config.metrics import (
    ACTIVE_REQUESTS,
    HTTP_ERROR_COUNT,
    HTTP_REQUEST_COUNT,
    HTTP_REQUEST_DURATION,
    prometheus_available,
)

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional OpenTelemetry
# ---------------------------------------------------------------------------

_otel_available: bool = False

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    _otel_available = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Metrics middleware
# ---------------------------------------------------------------------------


class _MetricsMiddleware(BaseHTTPMiddleware):
    """Collects Prometheus metrics for each HTTP request.

    Records: request duration (histogram), request count (counter),
    error count (counter for 5xx), and in-flight request gauge.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not prometheus_available:
            return await call_next(request)

        method = request.method
        endpoint = request.url.path

        if ACTIVE_REQUESTS is not None:
            ACTIVE_REQUESTS.inc()

        start = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except BaseException:
            status_code = 500
            raise
        finally:
            duration = time.monotonic() - start
            if HTTP_REQUEST_DURATION is not None:
                HTTP_REQUEST_DURATION.labels(
                    method=method, endpoint=endpoint, status_code=str(status_code)
                ).observe(duration)
            if HTTP_REQUEST_COUNT is not None:
                HTTP_REQUEST_COUNT.labels(
                    method=method, endpoint=endpoint, status_code=str(status_code)
                ).inc()
            if status_code >= 500 and HTTP_ERROR_COUNT is not None:
                HTTP_ERROR_COUNT.labels(method=method, endpoint=endpoint).inc()
            if ACTIVE_REQUESTS is not None:
                ACTIVE_REQUESTS.dec()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def setup_monitoring(app: FastAPI) -> None:
    """Attach monitoring instrumentation to a FastAPI application.

    Attempts OpenTelemetry instrumentation first (if the optional package is
    installed), then falls back to a Prometheus-based middleware.  Always
    exposes a ``GET /metrics`` endpoint when ``prometheus_client`` is
    available.
    """
    # 1. OpenTelemetry instrumentation (preferred for traces)
    if _otel_available:
        try:
            FastAPIInstrumentor.instrument_app(app)
            _log.info("OpenTelemetry FastAPI instrumentation active")
        except Exception:
            _log.warning("OpenTelemetry instrumentation failed, falling back to Prometheus")

    # 2. Prometheus-based middleware (metrics always collected)
    app.add_middleware(_MetricsMiddleware)

    # 3. /metrics endpoint
    if prometheus_available:
        _add_metrics_endpoint(app)
        _log.info("Prometheus /metrics endpoint registered")
    else:
        _log.info("Install prometheus-client for /metrics scraping endpoint")


def _add_metrics_endpoint(app: FastAPI) -> None:
    """Register a ``GET /metrics`` route returning Prometheus text format."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    @app.get("/metrics", include_in_schema=False, tags=["meta"])
    async def metrics() -> Response:
        """Prometheus metrics endpoint -- scraped by Prometheus / Grafana."""
        data = generate_latest()
        return Response(
            content=data,
            media_type=CONTENT_TYPE_LATEST,
            headers={"X-Robots-Tag": "noindex"},
        )
