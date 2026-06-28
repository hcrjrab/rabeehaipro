"""Structured logging setup.

Why two formatters?
- ``console`` (default in dev): human-readable, colorised, fast to scan.
- ``json`` (prod): one JSON object per line so Loki/Datadog/CloudWatch can
  parse structured fields without regex.

All loggers emit a ``request_id`` / ``session_id`` when present in the
contextvar so a single user flow can be traced across coroutines and
processes (esp. useful once Celery workers are added in Phase 6).
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, ClassVar

from .settings import get_settings

# Context vars are populated by middleware (Phase 2 API layer).
# Declared here so any module can read/write correlation ids.
_CORRELATION: dict[str, Any] = {}


def bind_context(**kwargs: Any) -> None:
    """Attach correlation ids (request_id, session_id, task_id, ...).

    These are merged into every subsequent log record produced by the
    ``_JsonFormatter`` / ``_ConsoleFormatter`` until cleared.
    """
    _CORRELATION.update(kwargs)


def clear_context() -> None:
    """Reset correlation context (call at end of request/task)."""
    _CORRELATION.clear()


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per record, suitable for log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        payload.update(_CORRELATION)
        # Attach any structured extras the caller passed via logger.info(..., extra=)
        for key, value in record.__dict__.items():
            if key in payload or key.startswith("_"):
                continue
            if key in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "taskName",
                "message",
            }:
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


class _ConsoleFormatter(logging.Formatter):
    """Readable single-line formatter with optional color."""

    _COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self._COLORS.get(record.levelname, "")
        base = f"{color}%(asctime)s %(levelname)-7s %(name)s %(message)s{self._RESET}"
        correlation = " ".join(f"{k}={v}" for k, v in _CORRELATION.items())
        fmt = base + (f" [{correlation}]" if correlation else "")
        return logging.Formatter(fmt, "%H:%M:%S").format(record)


def configure_logging() -> None:
    """Idempotently configure root logging from settings.

    Safe to call multiple times: re-attaches handlers only if the level/handlers
    differ, preventing duplicate lines on FastAPI reload.
    """
    settings = get_settings()
    root = logging.getLogger()

    desired_level = settings.log_level
    if root.level != (level := getattr(logging, desired_level, logging.INFO)):
        root.setLevel(level)

    formatter = _JsonFormatter() if settings.log_format == "json" else _ConsoleFormatter()

    # Replace any prior handlers we added to avoid duplication on reload.
    for h in list(root.handlers):
        if getattr(h, "_rabeeh_owned", False):
            root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler._rabeeh_owned = True  # type: ignore[attr-defined]
    root.addHandler(handler)

    # Tame noisy third-party loggers without silencing errors.
    for noisy in ("httpx", "httpcore", "urllib3", "watchfiles", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
