"""Rabeeh AI Agent Pro - Core package.

A production-grade autonomous AI desktop agent framework.

The public API surface is intentionally small at this stage:

>>> from rabeeh_core import get_settings, create_app

Internals are organised by bounded context (config, security, llm,
memory, agents, tools, orchestration, api, infra) following a pragmatic
Clean / Hexagonal architecture.
"""

from __future__ import annotations

from typing import Any

__version__ = "0.1.0"
__all__ = ["__version__", "create_app", "get_settings"]


def __getattr__(name: str) -> Any:  # pragma: no cover - thin lazy shim
    """Lazy attribute access so importing the top-level package is cheap.

    Heavy submodules (FastAPI app, settings) are only constructed when
    actually requested. This keeps CLI entrypoints and tests fast.
    """
    if name == "get_settings":
        from .config.settings import get_settings as _gs

        return _gs
    if name == "create_app":
        from .api.app import create_app as _ca

        return _ca
    raise AttributeError(f"module 'rabeeh_core' has no attribute {name!r}")
