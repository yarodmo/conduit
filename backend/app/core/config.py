"""
Conduit Backend — Core Configuration
Pydantic Settings for type-safe environment variable management.
"""

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

    # ── JWT ──
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

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

    model_config = {"env_file": ".env.local", "env_file_encoding": "utf-8"}


settings = Settings()
