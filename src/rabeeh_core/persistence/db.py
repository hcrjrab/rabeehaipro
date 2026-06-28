"""Async engine + session factory with graceful degradation.

The engine is created lazily on first use. We probe connectivity once at
init; if it fails, :func:`db_available` returns ``False`` and the repository
falls back to the in-memory store — so a missing/running Postgres never
prevents the app from serving requests.

Two URL schemes are supported out of the box:
- ``postgresql+psycopg://...``  -> production / docker.
- ``sqlite+aiosqlite:///path``   -> zero-config local dev (a file DB).
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config.settings import get_settings
from .models import Base

_log = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_available: bool | None = None  # tri-state: None = not probed yet


def _build_engine() -> AsyncEngine:
    """Construct the async engine from the configured database URL.

    SQLite URLs are rewritten to the async ``aiosqlite`` driver if the user
    supplied a plain ``sqlite://`` URL, so dev "just works" without remembering
    the driver suffix.
    """
    settings = get_settings()
    url = settings.database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("sqlite://") and "+aiosqlite" not in url:
        url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)

    engine = create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,  # detect dropped connections (Postgres idle timeout)
        future=True,
    )
    _log.debug("DB engine built for %s", settings._mask_url(url))
    return engine


def get_engine() -> AsyncEngine:
    """Return the cached async engine, building it on first access."""
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the cached session factory bound to the engine."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


def db_available() -> bool:
    """True if the DB was successfully probed at init.

    Returns ``False`` (graceful degradation) rather than raising once the
    probe has completed, so callers can branch without try/except noise.
    """
    if _available is None:
        _log.warning("db_available() called before init_db(); assuming false.")
        return False
    return _available


async def init_db() -> bool:
    """Probe connectivity and create tables if missing.

    Sets the module-level availability flag. Safe to call multiple times.
    Returns the availability flag so callers can branch on the result.
    """
    global _available
    if _available is True:
        return True  # already healthy; nothing to do

    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _available = True
        _log.info("DB initialised and available (%s tables).", len(Base.metadata.tables))
    except Exception as exc:
        _available = False
        _log.warning("DB unavailable; persistence will degrade to in-memory. (%s)", exc)
    return _available


async def close_db() -> None:
    """Dispose the engine pool (shutdown / tests)."""
    global _engine, _session_factory, _available
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
    _available = None


async def reset_for_tests() -> None:
    """Fully reset the persistence layer (tests / hot reload)."""
    await close_db()
