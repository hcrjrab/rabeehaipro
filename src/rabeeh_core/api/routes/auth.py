"""Authentication endpoints.

``POST /auth/login``   - authenticate with username + password
``POST /auth/refresh`` - exchange a refresh token for a new access token
``POST /auth/logout``  - revoke the current access token
``GET  /auth/me``      - return the current user's profile (for testing)
"""

from __future__ import annotations

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...config.settings import get_settings
from ..auth import (
    TokenPayload,
    create_access_token,
    create_refresh_token,
    get_current_user,
    invalidate_token,
    verify_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    access_token: str


class UserResponse(BaseModel):
    username: str
    role: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _verify_password(plain: str, hashed: str) -> bool:
    """Compare a plaintext password against a bcrypt hash."""
    try:
        ok: bool = bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        return ok
    except (ValueError, TypeError):
        return False


def _hash_password(plain: str) -> str:
    """Return the bcrypt hash of *plain*."""
    hashed: str = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    return hashed


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    """Authenticate with username and password.

    Returns a short-lived **access_token** (default 60 min) and a longer-lived
    **refresh_token** (default 7 days). The access token must be sent in the
    ``Authorization: Bearer <token>`` header for protected endpoints.
    """
    settings = get_settings()

    # Validate credentials
    expected_user = settings.auth_admin_username
    expected_pw = settings.auth_admin_password.get_secret_value()

    if body.username != expected_user or not _verify_password(
        body.password, _hash_password(expected_pw)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Issue tokens
    payload = {"sub": body.username, "role": "admin"}
    access = create_access_token(payload)
    refresh = create_refresh_token(payload)

    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair."""
    payload = verify_token(body.refresh_token)

    # Must be a refresh token
    if not payload.get("refresh", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provided token is not a refresh token",
        )

    # Issue new pair
    new_payload = {"sub": payload["sub"], "role": payload.get("role", "user")}
    access = create_access_token(new_payload)
    new_refresh = create_refresh_token(new_payload)

    # Revoke the old refresh token so it cannot be replayed
    invalidate_token(body.refresh_token)

    return TokenResponse(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=204)
async def logout(body: LogoutRequest) -> None:
    """Revoke an access token.

    The token is added to the in-memory blacklist and will be rejected on
    subsequent requests.
    """
    invalidate_token(body.access_token)


@router.get("/me", response_model=UserResponse)
async def me(current_user: TokenPayload = Depends(get_current_user)) -> UserResponse:  # noqa: B008
    """Return the current authenticated user's profile."""
    return UserResponse(username=current_user.sub, role=current_user.role)
