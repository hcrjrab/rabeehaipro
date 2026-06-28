"""Human-in-the-loop approval gate.

Every tool call the agent wants to execute passes through this gate before
running. The gate decides one of three outcomes:

- ``ALLOW``   -> execute immediately.
- ``DEFER``   -> pause and ask the user (via API / UI).
- ``DENY``    -> never allowed (policy block, e.g. credential misuse).

Decision logic combines a global policy (``Settings.approval_level``) with
per-call risk classification and an explicit allow-list of safe tools.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ..config.schemas import RiskLevel, ToolCallRequest
from ..config.settings import Settings, get_settings


class _SettingsGetter(Protocol):
    """Indirection so tests can inject a custom Settings."""

    def __call__(self) -> Settings: ...


# A callback the orchestrator registers: ``should_approve(call) -> bool``.
# Returning True yields ``DEFER``; the orchestrator then publishes an
# approval-request event and waits for the user.
ApprovalCallback = Callable[[ToolCallRequest], bool]


class ApprovalDecision(StrEnum):
    ALLOW = "allow"
    DEFER = "defer"
    DENY = "deny"


@dataclass(frozen=True)
class _Verdict:
    decision: ApprovalDecision
    reason: str


class ApprovalGate:
    """Stateless policy evaluator for tool calls.

    Encapsulates *all* policy so the orchestrator stays focused on flow
    control. Swap the policy by constructing with a different ``settings``.
    """

    # Tools that are intrinsically safe: no side effects, no secrets.
    SAFE_TOOLS: frozenset[str] = frozenset(
        {
            "file.read",
            "file.list",
            "file.stat",
            "web.search",
            "web.fetch",
            "memory.recall",
            "vision.describe",
            "screen.read",
            "screenshot",
        }
    )

    # Tools that can move money / spend or otherwise must NEVER run silently.
    ELEVATED_TOOLS: frozenset[str] = frozenset(
        {"payment.send", "email.send_bulk", "deploy.execute", "credential.use"}
    )

    def __init__(
        self,
        settings_getter: _SettingsGetter = get_settings,
    ) -> None:
        self._get_settings = settings_getter

    def evaluate(self, call: ToolCallRequest) -> _Verdict:
        """Return the verdict for a tool call under the current policy."""
        settings = self._get_settings()

        # 1. Hard blocks take precedence over everything.
        if call.tool_name in self.ELEVATED_TOOLS and call.risk != RiskLevel.ELEVATED:
            # Mis-classified elevated tool: fail closed.
            return _Verdict(
                ApprovalDecision.DENY,
                f"{call.tool_name} is policy-elevated but classified {call.risk}; refusing.",
            )

        # 2. Global "ask everything" mode.
        if settings.approval_level == "all":
            return _Verdict(ApprovalDecision.DEFER, "policy=approval_level(all)")

        # 3. Explicitly safe tools always pass (unless caller opted out).
        if call.tool_name in self.SAFE_TOOLS and call.risk == RiskLevel.NONE:
            return _Verdict(ApprovalDecision.ALLOW, "safe-tool-list")

        # 4. Risk-driven deferral.
        if call.risk in {RiskLevel.DESTRUCTIVE, RiskLevel.ELEVATED}:
            if settings.approval_level == "none":
                # Operator explicitly disabled approvals; permit but flag.
                return _Verdict(ApprovalDecision.ALLOW, "policy=approval_level(none), risk-flagged")
            return _Verdict(
                ApprovalDecision.DEFER,
                f"risk={call.risk} requires approval",
            )

        # 5. SAFE-level reversible side effects.
        if call.risk == RiskLevel.SAFE and settings.env != "prod":
            # In dev/staging, allow SAFE actions silently to keep flow smooth.
            return _Verdict(ApprovalDecision.ALLOW, "safe-risk, non-prod")

        # 6. Default: defer in prod, allow elsewhere. Fail-safe.
        if settings.env == "prod":
            return _Verdict(ApprovalDecision.DEFER, "default-prod-defer")
        return _Verdict(ApprovalDecision.ALLOW, "default-allow-nonprod")
