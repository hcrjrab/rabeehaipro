# Rabeeh AI Agent Pro

A production-grade autonomous AI desktop agent framework — comparable in
ambition to OpenAI Operator, Claude Computer Use, Manus AI, Browser Use,
Open Interpreter, and AutoGen.

> **Status:** Release Candidate (v0.6.0) — 413 tests passing, 0 mypy errors,
> Ruff clean, frontend build green. Ready for production hardening.

## What's in this repository (v0.6.0)

A full-stack autonomous AI agent framework with 11 specialist agent roles,
22+ tools, dual orchestrators, persistent memory, and a dark-themed Next.js UI.

| Context | Responsibility |
|---|---|
| `config` | Validated settings (Pydantic v2), structured logging, shared schemas |
| `security` | JWT auth + RBAC + rate limiting + secret encryption + approval gate |
| `llm` | Provider-agnostic client (LiteLLM/Ollama/Mock) + capability detection |
| `agents` | 11 agents: planner, reviewer, coding, research, browser, vision, automation, business, office, file, memory |
| `tools` | 22+ tools: builtin, file, code, browser, vision, computer-use, office, PDF |
| `memory` | Layered Memory (conversation + vector + knowledge graph) with 3 backends |
| `orchestration` | Dual runners: linear (runner.py) + LangGraph StateGraph (graph.py) |
| `api` | FastAPI app with health/monitoring/agents/tools/tasks/business/auth endpoints |
| `frontend` | Next.js 5-page dark UI with WebSocket streaming + Electron shell |

The whole stack runs **offline** against the in-process `MockLLMClient`, so
the architecture is fully exercisable before any cloud key is configured.

## Quick start

### 1. Install (editable, with dev tooling)

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -e ".[dev]"
```

### 2. Configure

```bash
copy .env.example .env            # Windows
# edit .env — defaults boot in dev with zero changes
```

### 3. Run the API

```bash
rabeeh serve --reload
# or: uvicorn rabeeh_core.infra.server:app --reload
```

Healthchecks: <http://127.0.0.1:8000/healthz>, `/readyz`, `/info`.

### 4. Run the tests

```bash
pytest
```

### 5. Bring up the data plane (optional, for later phases)

```bash
docker compose -f deploy/docker-compose.yml up -d   # postgres + redis + ollama
```

## Architecture at a glance

```
            ┌──────────────────────── FastAPI (api) ────────────────────────┐
            │  /healthz  /readyz  /info  /agents  /tools  /tasks             │
            └─────────────────────────────┬──────────────────────────────────┘
                                          │
                            ┌─────────────▼──────────────┐
                            │      Orchestrator          │  plan → execute → review
                            │  (orchestration/runner)    │  every step audited
                            └─────┬──────────┬───────────┘
                                  │          │
                  ┌───────────────▼┐  ┌──────▼───────────────┐
                  │   Agents       │  │  ApprovalGate        │  human-in-the-loop
                  │  (BaseAgent)   │  │  (security)          │  risk-classified
                  └───────┬────────┘  └──────────┬───────────┘
                          │                      │
                  ┌───────▼────────┐    ┌────────▼─────────┐
                  │  LLMClient     │    │   ToolRegistry    │  confined, audited
                  │ ollama/cloud/  │    │ file.read / echo  │  side-effect surface
                  │ mock           │    │  (+ Phase 3..)    │
                  └────────────────┘    └───────────────────┘
                          │
                  ┌───────▼────────┐
                  │  MemoryStore   │  conversation / project / long-term
                  │ in-memory now  │  ChromaDB in Phase 5
                  └────────────────┘
```

**Safety model.** Agents never touch the OS directly. They emit
`ToolCallRequest` objects; the orchestrator routes each through the
`ApprovalGate`, which classifies risk (`none`/`safe`/`destructive`/`elevated`)
and either allows, defers (asks the user), or denies. Filesystem tools are
path-confined to the workspace. Production refuses to boot with placeholder
secrets.

## Roadmap (all phases delivered)

- ✅ **Phase 1** — Scaffold, config, logging, security, LLM router, agent/tool/memory abstractions, FastAPI skeleton, auditable orchestrator, tests, docker-compose infra.
- ✅ **Phase 2** — LiteLLM local/cloud router with graceful fallback; Planner & Reviewer agents; LangGraph `StateGraph` execution loop; Postgres task/event persistence.
- ✅ **Phase 3** — File/Office/PDF tools; vision (OpenCV + EasyOCR); computer-use (mouse/keyboard/screen/clipboard).
- ✅ **Phase 4** — Browser agent (Playwright), Research agent, Coding agent (code execution).
- ✅ **Phase 5** — Business modules (quote/invoice/PO/BOQ/estimation); ChromaDB vector memory + knowledge graph.
- ✅ **Phase 6** — Security hardening (RBAC, JWT, audit log), Celery workers, observability (metrics/tracing).
- ✅ **Phase 7** — Next.js + Electron dark UI, packaging, CI/CD.

## Project layout

```
src/rabeeh_core/
  config/      settings, logging, schemas, metrics (Prometheus)
  security/    JWT auth, RBAC, secret vault, approval gate
  llm/         base protocol + litellm/ollama/openrouter/mock + capability detection
  agents/      BaseAgent + 11 specialist agents
  tools/       BaseTool + 22+ tools in 8 packs
  memory/      MemoryStore protocol + in-memory/Postgres/ChromaDB/KG
  orchestration/  state + linear runner + LangGraph StateGraph
  api/         FastAPI routes (health, agents, tools, tasks, auth, business, monitoring)
  business/    CRM + ERP entities (customers, vendors, quotes, invoices, PO, BOQ, inventory, estimation)
  infra/       ASGI entrypoint, Celery worker
  tasks/       Celery async task wrappers
  cli.py       `rabeeh` console script (serve/run/info)
tests/         413 tests (pytest, coverage ~69%)
alembic/       DB migration scripts (14 tables)
frontend/      Next.js + Electron dark UI
deploy/        docker-compose for postgres/redis/ollama
Dockerfile     multi-stage backend + frontend
```

## License

Proprietary. © Rabeeh AI.
