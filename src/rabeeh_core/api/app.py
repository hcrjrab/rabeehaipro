"""FastAPI application factory.

Lifecycle (``lifespan``):
- on startup: configure logging, log the effective settings (masked).
- on shutdown: close the shared LLM client's HTTP pools.

Routes are mounted from :mod:`rabeeh_core.api.routes`. CORS is enabled for
the configured origins so the Electron/Next frontend can call the API in dev.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config.logging import configure_logging
from ..config.settings import get_settings
from ..llm.registry import reset_client
from ..persistence.db import close_db, init_db
from ..tools.browser import close_browser

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hooks.

    Logging is (re)configured here rather than at import time so test
    clients that build their own app don't fight over handler state.

    DB init is best-effort: failure degrades to in-memory persistence
    rather than crashing the boot (see :mod:`rabeeh_core.persistence.db`).
    """
    settings = get_settings()
    configure_logging()
    _log.info("Starting %s | %s", settings.app_name, settings.log_safe())

    # Probe DB; non-fatal if unreachable (repository falls back to in-memory).
    await init_db()

    yield  # ---- app runs ----

    _log.info("Shutting down %s", settings.app_name)
    await reset_client()
    await close_browser()
    await close_db()


def create_app() -> FastAPI:
    """Construct and return the configured FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Production-grade autonomous AI desktop agent.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes are imported lazily to avoid importing heavy deps (httpx, etc.)
    # unless the API is actually used.
    from ..business.routes import router as business_router  # registers models before init_db
    from .auth import get_current_user
    from .middleware import add_rate_limiting
    from .routes import agents, chat, health, tasks, tools
    from .routes import auth as auth_routes

    # ---- Auth router (no auth required) ----
    app.include_router(auth_routes.router)

    # ---- Open routers (health probes, info) ----
    app.include_router(health.router, tags=["meta"])

    # ---- Protected routers (require valid Bearer token) ----
    app.include_router(
        agents.router, prefix="/agents", tags=["agents"], dependencies=[Depends(get_current_user)]
    )
    app.include_router(
        tasks.router, prefix="/tasks", tags=["tasks"], dependencies=[Depends(get_current_user)]
    )
    app.include_router(
        tools.router, prefix="/tools", tags=["tools"], dependencies=[Depends(get_current_user)]
    )
    app.include_router(chat.router, tags=["chat"], dependencies=[Depends(get_current_user)])
    app.include_router(business_router, dependencies=[Depends(get_current_user)])

    # ---- Rate limiting (last so it wraps all routes) ----
    add_rate_limiting(app)

    # ---- Monitoring & instrumentation ----
    from .monitoring import setup_monitoring

    setup_monitoring(app)

    # ---- Request correlation & timing  ----
    from .middleware import CorrelationIdMiddleware, RequestTimingMiddleware

    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(RequestTimingMiddleware)

    return app
