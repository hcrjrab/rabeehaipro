# Architecture Decision Records

## ADR-001: Streaming as Optional Protocol Method
**Status**: Accepted (2026-06-28)

**Context**: Not all providers support streaming (some local models, certain API endpoints). Callers shouldn't need to branch on provider type.

**Decision**: Added `chat_stream()` to the `LLMClient` Protocol with a default implementation that wraps the non-streaming `chat()` into a single `done` event. Providers override for true streaming. AsyncIterator return type composes naturally with `async for`.

**Consequences**: All providers support streaming trivially; streaming-optimised providers (Ollama, OpenRouter, LiteLLM) yield real token deltas.

---

## ADR-002: Capability Detection via Pattern Registry
**Status**: Accepted (2026-06-28)

**Context**: Different LLM models have different capabilities (vision, tools, context window). The router needs to match tasks to capable providers without requiring an API call to probe.

**Decision**: Curated pattern-to-capability registry in `capabilities.py`. Patterns are compiled regexes matched against model ID strings. Unknown models get conservative defaults.

**Consequences**: Zero-latency capability lookup. Registry must be maintained as new models emerge.

---

## ADR-003: MemoryRecord Replaces `role` with `kind`
**Status**: Accepted (2026-06-28)

**Context**: The original `MemoryRecord` had a `role` field mirroring chat message roles, but this conflated conversation role (user/assistant/tool) with memory type (insight/fact/preference).

**Decision**: Replaced `role` with `kind` (a semantic category: "chat", "tool_result", "plan", "error", "insight"). The original role is stored in `metadata.role`.

**Consequences**: Cleaner separation of concerns for the vector and knowledge graph stores. Existing chat messages use `kind="chat"` with role in metadata.

---

## ADR-004: Three-Tier Memory Architecture
**Status**: Accepted (2026-06-28)

**Context**: The master plan calls for conversation memory, long-term vector memory, and knowledge graph. These have fundamentally different query patterns and storage requirements.

**Decision**: Three separate protocol interfaces (`MemoryStore`, `VectorMemoryStore`, `KnowledgeGraph`) coordinated by the `MemoryService` composite.

**Consequences**: Each backend can be implemented, tested, and scaled independently. The composite provides a unified API for agents.

---

## ADR-005: LiteLLM as Optional Extra
**Status**: Accepted (2026-06-28)

**Context**: LiteLLM brings in 30+ transitive dependencies. Not all deployments need it (e.g., users running only Ollama locally).

**Decision**: LiteLLM is an optional extra (`pip install rabeeh-core[litellm]`). The provider checks for import availability and degrades gracefully with a clear error message.

**Consequences**: Minimal dependency footprint for basic usage. LiteLLM users get access to 100+ model providers.

---

## ADR-006: Async-Only Memory Protocol
**Status**: Accepted (2026-06-28)

**Context**: The original `InMemoryStore` was synchronous for simplicity. However, the PostgreSQL and ChromaDB backends are inherently async (network I/O).

**Decision**: All `MemoryStore` protocol methods are now async. `InMemoryStore` uses `async def` even though its implementation is synchronous.

**Consequences**: Clean interface consistency. Minor overhead for in-memory operations (event loop scheduling).
