"""Prometheus metrics definitions.

All metrics are defined lazily: importing this module does not require
``prometheus_client`` to be installed.  If the library is missing every
metric is ``None`` and the monitoring middleware becomes a no-op.
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Gauge, Histogram

    HTTP_REQUEST_DURATION = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        labelnames=["method", "endpoint", "status_code"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    )
    HTTP_REQUEST_COUNT = Counter(
        "http_requests_total",
        "Total HTTP requests",
        labelnames=["method", "endpoint", "status_code"],
    )
    HTTP_ERROR_COUNT = Counter(
        "http_errors_total",
        "Total HTTP 5xx errors",
        labelnames=["method", "endpoint"],
    )
    ACTIVE_REQUESTS = Gauge(
        "http_active_requests",
        "Current number of in-flight HTTP requests",
    )

    prometheus_available = True
    _log.debug("prometheus_client found -- metrics are live")
except ImportError:
    HTTP_REQUEST_DURATION = None  # type: ignore[assignment]
    HTTP_REQUEST_COUNT = None  # type: ignore[assignment]
    HTTP_ERROR_COUNT = None  # type: ignore[assignment]
    ACTIVE_REQUESTS = None  # type: ignore[assignment]
    prometheus_available = False
    _log.info("prometheus_client not installed; request metrics are no-ops")

# ---------------------------------------------------------------------------
# System metrics placeholders
# ---------------------------------------------------------------------------
# When ``psutil`` is available these should be set to:
#   MEMORY_USAGE = Gauge("system_memory_usage_bytes", "…", …)
#   CPU_USAGE    = Gauge("system_cpu_usage_percent", "…", …)

MEMORY_USAGE = None
CPU_USAGE = None
