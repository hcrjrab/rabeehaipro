"""Infrastructure helpers.

Cross-cutting runtime concerns that don't belong to a single bounded
context: graceful shutdown signal handling, a process-level async lock
for shared resources, and the ASGI app object exposed for ``uvicorn``.
"""

from __future__ import annotations

from .server import app  # re-exported ASGI app

__all__ = ["app"]
