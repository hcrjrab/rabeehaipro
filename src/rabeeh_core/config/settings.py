"""Centralised application settings.

Design decisions
----------------
1. **Single source of truth.** All tunables live here and are read from the
   environment (12-factor). Nothing else in the codebase should call
   ``os.getenv`` directly except this module.
2. **Fail fast / fail loud.** Pydantic v2 validates types on instantiation, so
   a misconfigured deployment raises immediately on boot rather than
   silently corrupting data at runtime.
3. **Secrets are never logged.** Every secret field is ``SecretStr`` and a
   custom ``log_safe()`` helper exists for diagnostics.
4. **Tiers.** ``env_file`` resolution lets developers drop a ``.env`` locally
   while Docker/CI inject real vars. ``dev``/``prod`` switch defaults via
   ``RABEEH_ENV``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,  # noqa: F401  (kept for downstream modules importing via here)
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
"""Absolute path to the repository root (3 levels up from this file)."""


class Settings(BaseSettings):
    """Strongly-typed, validated application configuration.

    All fields default to local-friendly values so the app boots with zero
    configuration, then harden for production by setting env vars.
    """

    model_config = SettingsConfigDict(
        env_prefix="RABEEH_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core runtime -----------------------------------------------------
    env: Literal["dev", "staging", "prod"] = "dev"
    app_name: str = "Rabeeh AI Agent Pro"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # --- Security ---------------------------------------------------------
    # Encryption key for secrets at rest (Fernet token). Auto-generated on
    # first boot in dev; MUST be supplied in prod.
    secret_key: SecretStr = SecretStr("dev-only-insecure-key-change-me")
    jwt_secret: SecretStr = SecretStr("dev-only-jwt-secret-change-me")
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60
    refresh_token_ttl_minutes: int = 10080
    auth_admin_username: str = "admin"
    auth_admin_password: SecretStr = SecretStr("dev-only-admin-pw-change-me")

    # --- Approval policy --------------------------------------------------
    # Operations classified at/above this level require explicit user approval
    # before execution. Drives the human-in-the-loop gate in the orchestrator.
    approval_level: Literal["none", "destructive", "all"] = "destructive"
    session_timeout_seconds: int = 1800

    # --- Databases / queues ----------------------------------------------
    database_url: str = "postgresql+psycopg://rabeeh:rabeeh@localhost:5432/rabeeh"
    redis_url: str = "redis://localhost:6379/0"
    chroma_path: Path = PROJECT_ROOT / ".data" / "chroma"
    sqlite_cache_path: Path = PROJECT_ROOT / ".data" / "cache.sqlite3"

    # --- LLM providers ----------------------------------------------------
    # ``prefer_local`` keeps tokens on-device when a capable local model is
    # available; cloud is used as fallback or for specialised tasks.
    default_provider: Literal["ollama", "openrouter", "litellm", "mock"] = "mock"
    prefer_local: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "qwen2.5:7b"
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_default_model: str = "openai/gpt-4o-mini"
    litellm_enabled: bool = False
    litellm_api_key: SecretStr = SecretStr("")
    litellm_api_base: str = ""
    litellm_default_model: str = "gpt-4o-mini"
    litellm_fallback_model: str = "gpt-4o-mini"
    litellm_max_retries: int = 2
    request_timeout_seconds: int = 90
    max_concurrent_llm_calls: int = 4
    streaming_enabled: bool = True
    streaming_chunk_size: int = 20

    # --- Agents -----------------------------------------------------------
    max_planner_steps: int = 8
    max_orchestrator_iterations: int = 20
    agent_temperature: float = 0.2

    # --- Paths ------------------------------------------------------------
    data_dir: Path = PROJECT_ROOT / ".data"
    logs_dir: Path = PROJECT_ROOT / ".data" / "logs"
    workspace_dir: Path = PROJECT_ROOT / "workspace"

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _enforce_prod_secrets(self) -> Settings:
        """In production, refuse to boot with the placeholder dev secrets."""
        if self.env == "prod":
            if self.secret_key.get_secret_value().startswith("dev-only"):
                raise ValueError("RABEEH_SECRET_KEY must be set in production.")
            if self.jwt_secret.get_secret_value().startswith("dev-only"):
                raise ValueError("RABEEH_JWT_SECRET must be set in production.")
            if self.auth_admin_password.get_secret_value().startswith("dev-only"):
                raise ValueError("RABEEH_AUTH_ADMIN_PASSWORD must be set in production.")
        return self

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def log_safe(self) -> dict[str, object]:
        """Return a dict safe to log (secrets masked)."""
        return {
            "env": self.env,
            "debug": self.debug,
            "host": self.host,
            "port": self.port,
            "log_level": self.log_level,
            "database_url": self._mask_url(self.database_url),
            "redis_url": self._mask_url(self.redis_url),
            "default_provider": self.default_provider,
            "prefer_local": self.prefer_local,
            "ollama_default_model": self.ollama_default_model,
            "approval_level": self.approval_level,
        }

    @staticmethod
    def _mask_url(url: str) -> str:
        """Hide credentials embedded in a DB/redis URL for log output."""
        if "://" in url and "@" in url:
            scheme, rest = url.split("://", 1)
            if "@" in rest:
                creds, host = rest.split("@", 1)
                return f"{scheme}://***:***@{host}"
        return url

    def ensure_directories(self) -> None:
        """Idempotently create runtime data directories."""
        for p in (self.data_dir, self.logs_dir, self.workspace_dir, self.chroma_path):
            p.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached, validated ``Settings`` singleton.

    Wrapped in ``lru_cache`` so the (relatively expensive) validation and
    ``.env`` parsing happens exactly once per process. Tests can clear the
    cache via ``get_settings.cache_clear()``.
    """
    settings = Settings()
    settings.ensure_directories()
    return settings
