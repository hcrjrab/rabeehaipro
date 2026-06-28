"""LLM router tests: failover + circuit-breaker behaviour."""

from __future__ import annotations

import pytest

from rabeeh_core.llm.base import LLMMessage, LLMResponse
from rabeeh_core.llm.mock import MockLLMClient
from rabeeh_core.llm.router import LLMRouter, _RouteHop, build_router


class _FailingClient:
    """Stand-in client that always raises, to exercise failover."""

    name = "failing"

    async def chat(self, *args, **kwargs):
        raise RuntimeError("boom")

    async def close(self) -> None:
        return None


class _EmptyClient:
    """Stand-in that returns an empty (``ok=False``) response."""

    name = "empty"

    async def chat(self, *args, **kwargs):
        return LLMResponse(content="", provider="empty")

    async def close(self) -> None:
        return None


def _hop(client, role="local") -> _RouteHop:
    return _RouteHop(client=client, role=role)


# ---------------------------------------------------------------------------
# Failover
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_router_fails_over_to_next_provider() -> None:
    """A failing primary must transparently yield to the next hop."""
    primary = _FailingClient()
    backup = MockLLMClient()
    backup.script("from-backup")
    router = LLMRouter([_hop(primary, "local"), _hop(backup, "cloud")], failure_threshold=10)

    resp = await router.chat([LLMMessage(role="user", content="hi")])
    assert resp.content == "from-backup"
    assert resp.provider == "mock"


@pytest.mark.asyncio
async def test_router_treats_empty_response_as_failure() -> None:
    """An empty (``ok=False``) response must trigger failover, not return."""
    primary = _EmptyClient()
    backup = MockLLMClient()
    backup.script("real-answer")
    router = LLMRouter([_hop(primary), _hop(backup)])

    resp = await router.chat([LLMMessage(role="user", content="hi")])
    assert resp.content == "real-answer"


@pytest.mark.asyncio
async def test_router_raises_when_all_hops_fail() -> None:
    """If every provider fails, the router must raise (not hang)."""
    router = LLMRouter(
        [_hop(_FailingClient(), "local"), _hop(_FailingClient(), "cloud")],
        failure_threshold=10,
    )
    with pytest.raises(RuntimeError, match="All .* providers failed"):
        await router.chat([LLMMessage(role="user", content="hi")])


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_circuit_opens_after_threshold_failures() -> None:
    """Repeated failures must open the circuit so the hop is skipped."""
    failing = _FailingClient()
    backup = MockLLMClient()
    # Script enough responses for the repeated successful probes of backup.
    backup.script(*["ok"] * 10)
    router = LLMRouter(
        [_hop(failing, "local"), _hop(backup, "cloud")], failure_threshold=3, cooldown_seconds=60.0
    )

    # Three failures trip the threshold.
    for _ in range(3):
        resp = await router.chat([LLMMessage(role="user", content="x")])
        assert resp.content == "ok"

    report = {h["provider"]: h for h in router.health_report()}
    assert report["failing"]["consecutive_failures"] == 3
    assert report["failing"]["circuit_open"] is True


@pytest.mark.asyncio
async def test_circuit_closes_after_cooldown() -> None:
    """After the cooldown elapses, a probe call is allowed again."""
    failing = _FailingClient()
    backup = MockLLMClient()
    backup.script(*["ok"] * 10)
    router = LLMRouter(
        [_hop(failing, "local"), _hop(backup, "cloud")],
        failure_threshold=2,
        cooldown_seconds=0.0,  # closes immediately
    )

    for _ in range(2):  # open the circuit
        await router.chat([LLMMessage(role="user", content="x")])

    # Cooldown is 0 -> next call probes the failing hop again (then fails over).
    resp = await router.chat([LLMMessage(role="user", content="x")])
    assert resp.content == "ok"


def test_build_router_mock_mode_is_single_hop() -> None:
    """In pure-mock mode the router is a trivial single-hop no-op."""
    router = build_router()
    assert len(router._hops) == 1
    assert router._hops[0].role == "mock"
