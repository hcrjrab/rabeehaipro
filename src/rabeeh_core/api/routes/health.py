"""Health & metadata endpoints.

``/healthz``  -> liveness (always 200 if the process is up).
``/readyz``   -> readiness (checks the LLM provider config is sane).
``/info``     -> version + masked settings for diagnostics.

These are intentionally cheap and dependency-free so they work even when
downstream services (DB/Redis) are down — important for orchestrators like
k8s/docker-compose that probe liveness independently of readiness.
"""

from __future__ import annotations

from fastapi import APIRouter

from ...config.settings import get_settings
from ...llm.registry import get_client

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe: process is reachable."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict[str, object]:
    """Readiness probe: provider configured + tool registry populated."""
    settings = get_settings()
    client = get_client()
    return {
        "status": "ok",
        "provider": client.name,
        "env": settings.env,
        "approval_level": settings.approval_level,
    }


@router.get("/info")
async def info() -> dict[str, object]:
    """Diagnostics: version + masked configuration."""
    settings = get_settings()
    return {
        "app": settings.app_name,
        "version": "0.1.0",
        "config": settings.log_safe(),
    }
