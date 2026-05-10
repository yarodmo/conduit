"""
Conduit Backend — Core Configuration
Pydantic Settings for type-safe environment variable management.
Extended for Sprint 1: JWT RS256, security params, rate limiting.
"""

import base64
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Application ──
    ENVIRONMENT: str = "development"
    APP_DEBUG: bool = False
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    SECRET_KEY: str = "CHANGE_ME"
    ALLOWED_ORIGINS: str = "http://localhost:5173"
    ALLOWED_HOSTS: str = "api.climbpeakdigital.com,conduit.blissystems.com,*.blissystems.com,localhost,127.0.0.1"

    # ── Database ──
    DATABASE_URL: str = "postgresql+asyncpg://conduit:conduit@localhost:5432/conduit"

    # ── Redis ──
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"

    # ── JWT RS256 (Prompt 3 Security) ──
    # Accepts base64-encoded key via env var (production) OR file path (dev)
    JWT_PRIVATE_KEY: str = ""
    JWT_PUBLIC_KEY: str = ""
    JWT_PRIVATE_KEY_PATH: str = "infrastructure/secrets/jwt-private.pem"
    JWT_PUBLIC_KEY_PATH: str = "infrastructure/secrets/jwt-public.pem"
    JWT_ALGORITHM: str = "RS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Security (Prompt 3) ──
    BCRYPT_ROUNDS: int = 12
    LOGIN_RATE_LIMIT_MAX: int = 5
    LOGIN_RATE_LIMIT_WINDOW: int = 900
    ACCOUNT_LOCKOUT_THRESHOLD: int = 10
    ACCOUNT_LOCKOUT_DURATION: int = 3600

    # ── AI ──
    DEFAULT_AI_MODEL: str = "claude-sonnet-4-5-20241022"
    LITELLM_MASTER_KEY: str = ""

    # ── Storage ──
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET_PLANS: str = "conduit-plans"
    S3_BUCKET_EXPORTS: str = "conduit-exports"
    S3_BUCKET_PHOTOS: str = "conduit-photos"
    S3_BUCKET_TILES: str = "conduit-tiles"

    # ── Email (Celery async — Prompt 3) ──
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@conduit.build"
    SMTP_FROM_NAME: str = "Conduit by Bliss Systems"

    # ── Frontend URLs (for email links) ──
    FRONTEND_URL: str = "http://localhost:5173"
    INVITATION_ACCEPT_URL: str = "{frontend_url}/accept-invite/{token}"
    PASSWORD_RESET_URL: str = "{frontend_url}/reset-password/{token}"

    # ── Observability ──
    SENTRY_DSN: str = ""
    LOKI_URL: str = "http://loki:3100"

    # ── Feature Flags ──
    FEATURE_M15_SIMULATION: bool = False
    FEATURE_AI_ASSISTANT: bool = True
    FEATURE_FIELD_SYNC: bool = True

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",")]

    @property
    def jwt_private_key(self) -> str:
        """RSA private key — base64 env var takes priority over file path."""
        if self.JWT_PRIVATE_KEY:
            return base64.b64decode(self.JWT_PRIVATE_KEY).decode()
        path = Path(self.JWT_PRIVATE_KEY_PATH)
        if not path.exists():
            if self.is_production:
                msg = f"JWT private key not found: set JWT_PRIVATE_KEY env var or place key at {path}"
                raise FileNotFoundError(msg)
            return ""
        return path.read_text()

    @property
    def jwt_public_key(self) -> str:
        """RSA public key — base64 env var takes priority over file path."""
        if self.JWT_PUBLIC_KEY:
            return base64.b64decode(self.JWT_PUBLIC_KEY).decode()
        path = Path(self.JWT_PUBLIC_KEY_PATH)
        if not path.exists():
            if self.is_production:
                msg = f"JWT public key not found: set JWT_PUBLIC_KEY env var or place key at {path}"
                raise FileNotFoundError(msg)
            return ""
        return path.read_text()

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
