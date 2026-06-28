# Changelog

## [0.6.0] - 2026-06-28 — Production Completion (Phases A–H)

### Added
- **Alembic database migrations**: `alembic/` directory with `env.py`, `script.py.mako`, initial migration (`initial_schema`) covering all 14 tables.
- **JWT Authentication**: `api/auth.py` with `create_access_token`, `create_refresh_token`, `verify_token`, token blacklist, `get_current_user` dependency, `require_role` RBAC factory.
- **Auth routes**: `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`.
- **Rate limiting**: `api/middleware.py` — in-memory sliding-window (60 req/min), exempts health & auth.
- **Celery async task execution**: `tasks/celery_app.py`, `tasks/orchestrator_tasks.py`, `tasks/worker.py` — async `run_goal` task with Redis broker/backend, graceful sync fallback, task status polling.
- **Monitoring**: `api/monitoring.py` — Prometheus metrics (`/metrics` endpoint), optional OpenTelemetry FastAPI instrumentation, `RequestTimingMiddleware`, `CorrelationIdMiddleware`.
- **Docker Compose**: `deploy/docker-compose.yml` — backend, frontend, postgres, redis, optional ollama.
- **GitHub Actions CI**: `.github/workflows/ci.yml` — ruff, mypy, pytest (with Postgres service), frontend build.
- **Makefile**: `install`, `dev`, `test`, `lint`, `typecheck`, `db-upgrade`, `docker-up`, `docker-down`.
- **frontend/Dockerfile**: Multi-stage Node build for production deployment.
- **Test coverage**: 7 new test suites (computer tools, vision tools, browser tools, memory stores, file tools, security, business repository), 238 new tests.
- **Ruff linting**: All source files formatted, all lint checks passing.

### Changed
- `PROJECT_STATUS.md`: Updated to Phase H, 413 tests, 69% coverage, 39+ endpoints.
- `pyproject.toml`: Added `PyJWT`, `celery`, `redis`, `opentelemetry-api`, `prometheus-client` dependencies; `rabeeh-worker` console script; monitoring extra.
- `api/app.py`: Auth router + middleware, monitoring setup, timing/correlation middlewares.
- `api/routes/tasks.py`: Celery submission with sync fallback, task status endpoint.
- `settings.py`: Added `refresh_token_ttl_minutes`, `auth_admin_username`, `auth_admin_password`.
- `tests/test_api.py`, `tests/test_business.py`: Updated for JWT auth fixtures.

## [0.5.0] - 2026-06-28 — Phase 2B: Security Hardening

### Added
- JWT Authentication (access + refresh tokens)
- Token Blacklist (in-memory)
- RBAC (require_role dependency)
- Rate Limiting (in-memory sliding window)
- Auth Routes (login, refresh, logout, me)
- Protected Routes (agents, tasks, tools, chat, business)

## [0.4.0] - 2026-06-28 — Phase 7: Business Modules

### Added
- Business ORM models (13 SQLAlchemy tables)
- Business Pydantic schemas (18 models)
- Business Repository with full CRUD for 8 entities
- Business API routes (19 endpoints)
- Business Agent with repository-backed operations
- Frontend API client for all business endpoints

## [0.3.0] - 2026-06-28 — Phase 5 + 6: Frontend & Electron Desktop

### Added
- shadcn/ui component library
- Dashboard, Chat, Tasks, Agents, Settings pages
- API client (all backend endpoints)
- Sidebar navigation, dark/light theme
- Electron main process, preload, IPC, system tray
- electron-builder cross-platform packaging config

## [0.2.0] - 2026-06-28 — Phase 2A + 2B: AI Runtime & Memory

### Added
- LiteLLM provider, streaming protocol, WebSocket endpoint
- Model capability detection, capability-aware routing
- Ollama/OpenRouter streaming
- ChromaDB vector memory, PostgreSQL conversation memory, SQLite KG
- Memory Agent, Business Agent (scaffold), MemoryService composite

## [0.1.0] - 2026-06-19 — Phase 1: Core Foundation

### Added
- Initial project scaffold, Clean Architecture
- 10 agents, 22+ tools, FastAPI API, LangGraph orchestration
- Security (Fernet encryption, approval gate), config, logging
- Persistence (SQLAlchemy + Repository pattern)
- Docker + Docker Compose infrastructure
- 14 test suites, 175 tests
