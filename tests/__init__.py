"""Test suite root.

Tests run with the in-process ``MockLLMClient`` and ``InMemoryStore`` so the
entire agent stack is exercised without network, GPU, or DB access:

    pytest

Coverage targets the core abstractions (config, security, llm, tools,
agents, orchestration) and the API surface.
"""
