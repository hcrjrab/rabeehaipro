"""API bounded context.

FastAPI application factory and HTTP/WebSocket routes. The app is created
via :func:`create_app` (factory pattern) so we can:

- Build differently configured apps for tests vs runtime.
- Attach lifespan handlers (startup/shutdown) cleanly.
- Keep import-time side effects out of the module top-level.
"""

from __future__ import annotations

from .app import create_app

__all__ = ["create_app"]
