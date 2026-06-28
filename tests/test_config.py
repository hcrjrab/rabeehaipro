"""Config + security unit tests."""

from __future__ import annotations

import pytest
from cryptography.fernet import InvalidToken
from pydantic import ValidationError

from rabeeh_core.config.schemas import RiskLevel, ToolCallRequest
from rabeeh_core.config.settings import Settings
from rabeeh_core.security import ApprovalDecision, ApprovalGate, SecretVault
from rabeeh_core.security.approval import _SettingsGetter  # noqa: F401 (kept for API surface)


def test_settings_defaults_are_dev_safe() -> None:
    """Default settings must boot in dev without any env vars."""
    s = Settings()  # type: ignore[call-arg]
    assert s.env == "dev"
    assert s.default_provider == "mock"
    assert s.approval_level == "destructive"


def test_settings_prod_requires_real_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production must refuse to boot with the placeholder dev secrets."""
    monkeypatch.setenv("RABEEH_ENV", "prod")
    # Plain dev secrets -> must raise.
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]

    # Real secret -> accepted.
    monkeypatch.setenv("RABEEH_SECRET_KEY", "real-strong-key")
    monkeypatch.setenv("RABEEH_JWT_SECRET", "real-jwt-key")
    monkeypatch.setenv("RABEEH_AUTH_ADMIN_PASSWORD", "real-admin-pw")
    s = Settings()  # type: ignore[call-arg]
    assert s.env == "prod"


def test_log_safe_masks_credentials() -> None:
    """``log_safe`` must never leak DB credentials embedded in a URL."""
    s = Settings(database_url="postgresql://user:secret@host:5432/db")  # type: ignore[call-arg]
    safe = s.log_safe()
    assert "secret" not in str(safe)
    assert "***" in str(safe)


def test_secret_vault_roundtrip() -> None:
    """Encrypt -> decrypt must be identity; tamper must fail."""
    vault = SecretVault(passphrase="master-passphrase")
    token = vault.encrypt("super-secret-api-key")
    assert token != "super-secret-api-key"
    assert vault.decrypt(token) == "super-secret-api-key"

    # Different passphrase -> cannot decrypt.
    other = SecretVault(passphrase="wrong-passphrase")

    with pytest.raises(InvalidToken):
        other.decrypt(token)


def test_approval_gate_safe_tool_is_allowed() -> None:
    """Read-only tools classified NONE must always be allowed."""
    gate = ApprovalGate()
    call = ToolCallRequest(tool_name="file.read", arguments={"path": "x"})
    verdict = gate.evaluate(call)
    assert verdict.decision is ApprovalDecision.ALLOW


def test_approval_gate_destructive_defers() -> None:
    """Destructive risk must defer for user approval (default policy)."""
    gate = ApprovalGate()
    call = ToolCallRequest(
        tool_name="file.write",
        arguments={"path": "x"},
        risk=RiskLevel.DESTRUCTIVE,
    )
    verdict = gate.evaluate(call)
    assert verdict.decision is ApprovalDecision.DEFER


def test_approval_gate_elevated_misclassification_denies() -> None:
    """An elevated tool classified below ELEVATED must be hard-denied."""
    gate = ApprovalGate()
    call = ToolCallRequest(
        tool_name="payment.send",
        arguments={},
        risk=RiskLevel.DESTRUCTIVE,  # too low for an elevated tool
    )
    verdict = gate.evaluate(call)
    assert verdict.decision is ApprovalDecision.DENY
