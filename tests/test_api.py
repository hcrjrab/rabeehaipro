"""API smoke tests via FastAPI's TestClient."""

from __future__ import annotations

from fastapi.testclient import TestClient

from rabeeh_core.api.app import create_app


def _client() -> TestClient:
    """Build a fresh app + client per test to avoid cross-test state."""
    return TestClient(create_app())


def _auth_headers(client: TestClient) -> dict[str, str]:
    """Return ``Authorization`` header for the default admin user."""
    r = client.post(
        "/auth/login", json={"username": "admin", "password": "dev-only-admin-pw-change-me"}
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_healthz_is_ok() -> None:
    with _client() as c:
        r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readyz_reports_provider() -> None:
    with _client() as c:
        r = c.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "mock"  # default provider in dev
    assert body["status"] == "ok"


def test_info_masks_secrets() -> None:
    """``/info`` must never leak the raw secret key."""
    with _client() as c:
        r = c.get("/info")
    assert r.status_code == 200
    body_text = r.text
    assert "dev-only-insecure-key-change-me" not in body_text


def test_tools_listed() -> None:
    with _client() as c:
        headers = _auth_headers(c)
        r = c.get("/tools", headers=headers)
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["tools"]}
    assert {"echo", "file.read", "file.list"} <= names


def test_tool_detail_404_for_unknown() -> None:
    with _client() as c:
        headers = _auth_headers(c)
        r = c.get("/tools/does-not-exist", headers=headers)
    assert r.status_code == 404


def test_agents_roles_listed() -> None:
    with _client() as c:
        headers = _auth_headers(c)
        r = c.get("/agents/roles", headers=headers)
    assert r.status_code == 200
    roles = set(r.json()["roles"])
    assert {"planner", "coding", "browser", "reviewer"} <= roles


def test_create_task_runs_to_completion() -> None:
    """Posting a goal must run the orchestrator and return a snapshot."""
    with _client() as c:
        headers = _auth_headers(c)
        r = c.post("/tasks", json={"goal": "say hello"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"completed", "awaiting_approval", "failed"}
    assert body["goal"] == "say hello"
    assert "events" in body


# ---------------------------------------------------------------------------
# Auth endpoint tests
# ---------------------------------------------------------------------------


def test_login_success() -> None:
    with _client() as c:
        r = c.post(
            "/auth/login", json={"username": "admin", "password": "dev-only-admin-pw-change-me"}
        )
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


def test_login_wrong_password() -> None:
    with _client() as c:
        r = c.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_wrong_username() -> None:
    with _client() as c:
        r = c.post(
            "/auth/login", json={"username": "nobody", "password": "dev-only-admin-pw-change-me"}
        )
    assert r.status_code == 401


def test_refresh_token_works() -> None:
    with _client() as c:
        login_r = c.post(
            "/auth/login", json={"username": "admin", "password": "dev-only-admin-pw-change-me"}
        )
        refresh_token = login_r.json()["refresh_token"]
        r = c.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_logout_revokes_token() -> None:
    with _client() as c:
        login_r = c.post(
            "/auth/login", json={"username": "admin", "password": "dev-only-admin-pw-change-me"}
        )
        token = login_r.json()["access_token"]
        # Logout
        r = c.post("/auth/logout", json={"access_token": token})
        assert r.status_code == 204
        # Token should now be rejected
        r2 = c.get("/tools", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 401


def test_auth_me_returns_user() -> None:
    with _client() as c:
        headers = _auth_headers(c)
        r = c.get("/auth/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "admin"
    assert body["role"] == "admin"


def test_missing_token_returns_401() -> None:
    with _client() as c:
        r = c.get("/tools")
    assert r.status_code == 401


def test_expired_token_returns_401() -> None:
    """An expired token should be rejected."""
    import time

    import jwt

    from rabeeh_core.config.settings import get_settings

    s = get_settings()
    secret = s.jwt_secret.get_secret_value()
    expired = jwt.encode(
        {"sub": "admin", "role": "admin", "exp": time.time() - 3600, "iat": time.time() - 7200},
        secret,
        algorithm=s.jwt_algorithm,
    )
    with _client() as c:
        r = c.get("/tools", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()
