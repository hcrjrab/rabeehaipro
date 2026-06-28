"""JWT authentication, token management, and RBAC.

Uses ``PyJWT`` (already present in the environment) with HS256 signing.
Tokens are validated against the configured ``jwt_secret`` from settings.

Design notes
------------
* **Stateless.** No database lookup on every request — user info is embedded in
  the token, signed, and verified with the shared secret.
* **Blacklist.** A per-process ``set`` holds tokens invalidated via logout.
  Production should replace this with Redis or a DB-backed store.
* **RBAC.** The ``require_role`` dependency factory gates routes by role.
  Roles are embedded in the token at creation time.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config.settings import get_settings

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token blacklist (in-memory; replace with Redis in production)
# ---------------------------------------------------------------------------
_blacklist: set[str] = set()

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

TOKEN_BEARER = HTTPBearer(auto_error=False)
"""FastAPI security scheme — Bearer token from the ``Authorization`` header."""


@dataclass
class TokenPayload:
    """Decoded JWT payload exposed to route handlers."""

    sub: str
    role: str = "user"
    exp: float = 0.0
    iat: float = 0.0
    jti: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenPayload:
        return cls(
            sub=data.get("sub", ""),
            role=data.get("role", "user"),
            exp=data.get("exp", 0.0),
            iat=data.get("iat", 0.0),
            jti=data.get("jti", ""),
            extra={k: v for k, v in data.items() if k not in ("sub", "role", "exp", "iat", "jti")},
        )


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------


def _now() -> float:
    """Current UTC timestamp as seconds since epoch."""
    return time.time()


def _gen_jti() -> str:
    """Generate a unique token ID (nanosecond timestamp + monotonic)."""
    import uuid

    return uuid.uuid4().hex


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token.

    Parameters
    ----------
    data:
        Claims to embed. Must contain at least ``sub`` (subject/user ID).
    expires_delta:
        Lifespan of the token. Defaults to the configured
        ``access_token_ttl_minutes``.

    Returns
    -------
    Encoded JWT string.
    """
    settings = get_settings()
    to_encode = data.copy()
    now = _now()
    expire = now + (
        expires_delta.total_seconds() if expires_delta else settings.access_token_ttl_minutes * 60
    )
    to_encode.update(
        {
            "exp": expire,
            "iat": now,
            "jti": _gen_jti(),
        }
    )
    secret = settings.jwt_secret.get_secret_value()
    return jwt.encode(to_encode, secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict[str, Any]) -> str:
    """Create a longer-lived JWT refresh token (default 7 days).

    The refresh token carries a ``refresh`` claim so the API can distinguish
    it from an access token and refuse to grant resource access with it.
    """
    settings = get_settings()
    to_encode = {**data, "refresh": True}
    now = _now()
    expire = now + settings.refresh_token_ttl_minutes * 60
    to_encode.update({"exp": expire, "iat": now, "jti": _gen_jti()})
    secret = settings.jwt_secret.get_secret_value()
    return jwt.encode(to_encode, secret, algorithm=settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------


def verify_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT.

    Raises
    ------
    HTTPException (401)
        If the token is expired, invalid, or blacklisted.
    """
    settings = get_settings()

    # 1. Blacklist check
    if token in _blacklist:
        _log.warning("Blacklisted token used")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    # 2. Decode / verify signature + expiry
    secret = settings.jwt_secret.get_secret_value()
    try:
        payload: dict[str, Any] = jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return payload


def invalidate_token(token: str) -> None:
    """Add *token* to the in-memory blacklist."""
    _blacklist.add(token)
    _log.info("Token %s … blacklisted (%d total)", token[:8], len(_blacklist))


def clear_blacklist() -> None:
    """Clear the in-memory blacklist (useful in tests)."""
    _blacklist.clear()


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(TOKEN_BEARER),  # noqa: B008
) -> TokenPayload:
    """Extract and validate the current user from the Bearer token.

    Use as a FastAPI dependency on any route that requires authentication.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = verify_token(credentials.credentials)

    # Reject refresh tokens used as access tokens
    if payload.get("refresh", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token cannot be used for resource access",
        )

    return TokenPayload.from_dict(payload)


def require_role(required_role: str) -> Callable[[TokenPayload], Coroutine[Any, Any, TokenPayload]]:
    """Create a dependency that enforces a minimum role.

    Usage::

        @router.get("/admin-only")
        async def admin_endpoint(user: TokenPayload = Depends(require_role("admin"))):
            ...
    """

    async def _role_checker(current_user: TokenPayload = Depends(get_current_user)) -> TokenPayload:  # noqa: B008
        # Role hierarchy: admin > manager > user
        hierarchy = {"admin": 3, "manager": 2, "user": 1}
        user_level = hierarchy.get(current_user.role, 0)
        required_level = hierarchy.get(required_role, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' or higher required",
            )
        return current_user

    return _role_checker
