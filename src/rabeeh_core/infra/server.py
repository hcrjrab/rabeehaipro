"""ASGI entrypoint.

Exposes a module-level ``app`` for ``uvicorn`` so deployment is simply:

    uvicorn rabeeh_core.infra.server:app --host 0.0.0.0 --port 8000

We construct the app eagerly (not lazily) because uvicorn imports this
module by path and expects ``app`` to be present immediately.
"""

from __future__ import annotations

from ..api.app import create_app

# Constructed once at import. Lifespan (DB/LLM init) runs on first request
# cycle via the ``lifespan`` context manager defined in api.app.
app = create_app()
