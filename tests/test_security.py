"""Security module tests — SecretVault, ApprovalGate."""

from __future__ import annotations

import pytest
from cryptography.fernet import InvalidToken

from rabeeh_core.config.schemas import RiskLevel, ToolCallRequest
from rabeeh_core.security import ApprovalDecision, ApprovalGate, SecretVault


class TestSecretVault:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        vault = SecretVault(passphrase="test-master-key-32-bytes!")
        token = vault.encrypt("my-secret-password")
        assert isinstance(token, str)
        assert token != "my-secret-password"
        plain = vault.decrypt(token)
        assert plain == "my-secret-password"

    def test_decrypt_wrong_key_fails(self) -> None:
        vault1 = SecretVault(passphrase="key-one-1234567890abcde")
        token = vault1.encrypt("secret")
        vault2 = SecretVault(passphrase="key-two-0987654321zyxwv")
        with pytest.raises(InvalidToken):
            vault2.decrypt(token)

    def test_encrypt_empty_string(self) -> None:
        vault = SecretVault(passphrase="test-key-1234567890abcde")
        token = vault.encrypt("")
        assert vault.decrypt(token) == ""

    def test_encrypt_unicode(self) -> None:
        vault = SecretVault(passphrase="unicode-key-1234567890abc")
        text = "héllo wörld 🔐"
        token = vault.encrypt(text)
        assert vault.decrypt(token) == text

    def test_different_tokens_for_same_plaintext(self) -> None:
        vault = SecretVault(passphrase="test-key-1234567890abcde")
        t1 = vault.encrypt("same")
        t2 = vault.encrypt("same")
        assert t1 != t2

    def test_uses_settings_by_default(self) -> None:
        from rabeeh_core.config.settings import get_settings

        get_settings.cache_clear()
        vault = SecretVault()
        token = vault.encrypt("auto-key-test")
        assert vault.decrypt(token) == "auto-key-test"


class TestApprovalGate:
    def _call(self, name: str, risk: RiskLevel = RiskLevel.NONE) -> ToolCallRequest:
        return ToolCallRequest(tool_name=name, arguments={}, rationale="test", risk=risk)

    def test_safe_tool_allowed(self) -> None:
        gate = ApprovalGate()
        result = gate.evaluate(self._call("file.read", RiskLevel.NONE))
        assert result.decision == ApprovalDecision.ALLOW

    def test_safe_tool_wrong_risk_nonprod_allowed(self) -> None:
        gate = ApprovalGate()
        result = gate.evaluate(self._call("file.read", RiskLevel.SAFE))
        assert result.decision == ApprovalDecision.ALLOW

    def test_elevated_tool_not_in_list_denied(self) -> None:
        gate = ApprovalGate()
        req = ToolCallRequest(
            tool_name="payment.send", arguments={}, rationale="test", risk=RiskLevel.SAFE
        )
        result = gate.evaluate(req)
        assert result.decision == ApprovalDecision.DENY

    def test_elevated_tool_proper_risk_allowed(self) -> None:
        gate = ApprovalGate()
        req = ToolCallRequest(
            tool_name="payment.send", arguments={}, rationale="test", risk=RiskLevel.ELEVATED
        )
        result = gate.evaluate(req)
        assert result.decision != ApprovalDecision.DENY

    def test_destructive_risk_defers(self) -> None:
        gate = ApprovalGate()
        result = gate.evaluate(self._call("file.delete", RiskLevel.DESTRUCTIVE))
        assert result.decision == ApprovalDecision.DEFER

    def test_safe_risk_nonprod_allowed(self) -> None:
        from rabeeh_core.config.settings import get_settings

        settings = get_settings()
        settings.env = "dev"
        gate = ApprovalGate()
        result = gate.evaluate(self._call("file.write", RiskLevel.SAFE))
        assert result.decision == ApprovalDecision.ALLOW

    def test_all_approval_mode_defers_everything(self) -> None:
        from rabeeh_core.config.settings import get_settings

        settings = get_settings()
        settings.approval_level = "all"
        gate = ApprovalGate()
        result = gate.evaluate(self._call("file.read", RiskLevel.NONE))
        assert result.decision == ApprovalDecision.DEFER

    def test_none_approval_level_allows_destructive(self) -> None:
        from rabeeh_core.config.settings import get_settings

        settings = get_settings()
        settings.approval_level = "none"
        gate = ApprovalGate()
        result = gate.evaluate(self._call("file.delete", RiskLevel.DESTRUCTIVE))
        assert result.decision == ApprovalDecision.ALLOW

    def test_prod_default_defers(self) -> None:
        from rabeeh_core.config.settings import get_settings

        settings = get_settings()
        settings.env = "prod"
        settings.approval_level = "destructive"
        gate = ApprovalGate()
        result = gate.evaluate(self._call("unknown.tool", RiskLevel.SAFE))
        assert result.decision == ApprovalDecision.DEFER

    def test_nonprod_default_allows_safe(self) -> None:
        gate = ApprovalGate()
        result = gate.evaluate(self._call("unknown.tool", RiskLevel.SAFE))
        assert result.decision == ApprovalDecision.ALLOW

    def test_approval_decision_enum_values(self) -> None:
        assert ApprovalDecision.ALLOW.value == "allow"
        assert ApprovalDecision.DEFER.value == "defer"
        assert ApprovalDecision.DENY.value == "deny"
