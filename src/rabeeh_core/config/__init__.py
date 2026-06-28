"""Configuration bounded context.

Owns all environment-driven configuration for the application:

- ``settings.py``        -> centralised, validated ``Settings`` (Pydantic v2).
- ``logging.py``         -> structured logging setup (JSON in prod, pretty in dev).
- ``schemas.py``         -> shared Pydantic schemas (enums, task/event shapes).

This module must have **no** runtime side effects on import so it can be
imported from anywhere without triggering DB/Redis connections.
"""

from __future__ import annotations

from .settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
