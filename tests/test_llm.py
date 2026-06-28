"""LLM client tests (mock + provider construction)."""

from __future__ import annotations

import json

import pytest

from rabeeh_core.llm.base import LLMMessage
from rabeeh_core.llm.mock import MockLLMClient
from rabeeh_core.llm.registry import build_default_client


@pytest.mark.asyncio
async def test_mock_client_returns_scripted_response() -> None:
    """Scripted responses must be returned FIFO, overriding heuristics."""
    client = MockLLMClient()
    client.script("first", "second")
    r1 = await client.chat([LLMMessage(role="user", content="hi")])
    r2 = await client.chat([LLMMessage(role="user", content="hi")])
    assert r1.content == "first"
    assert r2.content == "second"


@pytest.mark.asyncio
async def test_mock_client_plan_prompt_returns_json() -> None:
    """A plan-style prompt must yield parseable JSON with steps."""
    client = MockLLMClient()
    resp = await client.chat([LLMMessage(role="user", content="Please plan this for me")])
    payload = json.loads(resp.content)
    assert "steps" in payload and len(payload["steps"]) >= 1


@pytest.mark.asyncio
async def test_mock_client_reports_usage() -> None:
    """Usage tokens must be positive and consistent."""
    client = MockLLMClient()
    resp = await client.chat([LLMMessage(role="user", content="hello world")])
    assert resp.usage.prompt_tokens > 0
    assert resp.usage.total_tokens == resp.usage.prompt_tokens + resp.usage.completion_tokens


def test_build_default_client_mock_by_default() -> None:
    """The default provider (mock) must construct with no network."""
    client = build_default_client("mock")
    assert client.name == "mock"
    assert isinstance(client, MockLLMClient)


@pytest.mark.asyncio
async def test_unknown_provider_raises() -> None:
    """An unknown provider name must raise, not silently fall back."""
    with pytest.raises(ValueError):
        build_default_client("bogus")  # type: ignore[arg-type]
