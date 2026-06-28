"""Security bounded context.

Concerns owned here:
- At-rest encryption of secrets (Fernet) via :class:`SecretVault`.
- Approval policy evaluation (the human-in-the-loop gate).
- (Phase 6) RBAC, JWT issuance, audit log writer.

Kept dependency-light: only ``cryptography`` for Fernet, no framework
coupling, so it can be unit-tested in isolation.
"""

from __future__ import annotations

from .approval import ApprovalDecision, ApprovalGate
from .secrets import SecretVault

__all__ = ["ApprovalDecision", "ApprovalGate", "SecretVault"]
