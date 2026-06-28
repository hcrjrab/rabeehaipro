"""Shared pytest fixtures.

Centralises the "isolated world" each test wants:
- a fresh ``Settings`` (cache cleared) so tests don't leak config,
- a fresh mock LLM,
- a fresh tool registry + memory + orchestrator,
- an isolated async SQLite DB for persistence tests.

Tests that only need one piece can still import the helpers directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from rabeeh_core.business.repository import reset_business_repository
from rabeeh_core.config.settings import get_settings
from rabeeh_core.llm.mock import MockLLMClient
from rabeeh_core.orchestration.runner import Orchestrator, reset_orchestrator
from rabeeh_core.persistence import db as db_module
from rabeeh_core.persistence.repository import reset_repository
from rabeeh_core.tools.registry import get_registry, reset_registry


@pytest.fixture(autouse=True)
def _reset_singletons() -> Iterator[None]:
    """Ensure every test starts with fresh process-wide singletons.

    Resets the ``lru_cache`` on ``get_settings`` and the module-level
    ``_registry`` / orchestrator so state never bleeds across tests. Async
    cleanup (LLM client, DB engine) is handled by the dedicated fixtures.
    """
    get_settings.cache_clear()
    reset_registry()
    reset_orchestrator()
    reset_repository()
    reset_business_repository()
    db_module._available = None
    yield
    get_settings.cache_clear()
    reset_registry()
    reset_orchestrator()
    reset_repository()
    reset_business_repository()
    db_module._available = None


@pytest.fixture()
def mock_llm() -> MockLLMClient:
    """A fresh, scriptable mock LLM."""
    return MockLLMClient()


@pytest.fixture()
def orchestrator(mock_llm: MockLLMClient) -> Orchestrator:
    """An orchestrator wired to the mock LLM and default tool registry."""
    return Orchestrator(llm=mock_llm, tools=get_registry())


@pytest.fixture()
def dev_settings():  # type: ignore[no-untyped-def]
    """Default dev settings (already validated)."""
    return get_settings()


@pytest.fixture()
async def sqlite_db(tmp_path: Path) -> AsyncIterator[None]:
    """Point persistence at an isolated in-file SQLite DB for one test.

    Sets ``RABEEH_DATABASE_URL`` to a temp file, clears the settings cache,
    runs ``init_db`` (creates tables), and disposes the engine afterwards.
    Tests using this fixture exercise the *real* async SQLAlchemy path.
    """
    import os

    db_file = tmp_path / "test.db"
    os.environ["RABEEH_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    get_settings.cache_clear()
    db_module._available = None  # force a fresh probe
    try:
        await db_module.init_db()
        yield
    finally:
        await db_module.close_db()
        os.environ.pop("RABEEH_DATABASE_URL", None)
        get_settings.cache_clear()
