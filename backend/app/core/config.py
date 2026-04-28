"""
Conduit Backend — Core Configuration
Pydantic Settings for type-safe environment variable management.
Extended for Sprint 1: JWT RS256, security params, rate limiting.
"""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Application ──
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_SECRET_KEY: str = "CHANGE_ME"
    CORS_ORIGINS: str = "http://localhost:5173"

    # ── Database ──
    DATABASE_URL: str = "postgresql+asyncpg://conduit:conduit@localhost:5432/conduit"

    # ── Redis ──
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"

    # ── JWT RS256 (Prompt 3 Security) ──
    JWT_PRIVATE_KEY_PATH: str = "infrastructure/secrets/jwt-private.pem"
    JWT_PUBLIC_KEY_PATH: str = "infrastructure/secrets/jwt-public.pem"
    JWT_ALGORITHM: str = "RS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30  # v11: 30 days

    # ── Security (Prompt 3) ──
    BCRYPT_ROUNDS: int = 12
    LOGIN_RATE_LIMIT_MAX: int = 5
    LOGIN_RATE_LIMIT_WINDOW: int = 900  # 15 minutes in seconds
    ACCOUNT_LOCKOUT_THRESHOLD: int = 10
    ACCOUNT_LOCKOUT_DURATION: int = 3600  # 1 hour in seconds

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
    SMTP_FROM_EMAIL: str = "noreply@conduit.build"
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
        return self.APP_ENV == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def jwt_private_key(self) -> str:
        """Load RSA private key from file."""
        path = Path(self.JWT_PRIVATE_KEY_PATH)
        if not path.exists():
            if self.is_production:
                msg = f"JWT private key not found at {path}"
                raise FileNotFoundError(msg)
            # Dev fallback — generate in-memory (NOT for production)
            return ""
        return path.read_text()

    @property
    def jwt_public_key(self) -> str:
        """Load RSA public key from file."""
        path = Path(self.JWT_PUBLIC_KEY_PATH)
        if not path.exists():
            if self.is_production:
                msg = f"JWT public key not found at {path}"
                raise FileNotFoundError(msg)
            return ""
        return path.read_text()

    model_config = {"env_file": ".env.local", "env_file_encoding": "utf-8"}


settings = Settings()
