"""
Conduit Backend — FastAPI Application Entry Point
v11.0 Master Prompt: Sprint 1 — Auth, Projects & Plans Foundation

Bliss Systems LLC — APEX Standard
"""

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine, init_db
from app.core.redis import close_redis, init_redis
from app.middleware.error_handler import register_error_handlers
from app.modules.auth.router import router as auth_router
from app.modules.projects.router import router as projects_router

logger = structlog.get_logger()


# ══════════════════════════════════════
# LIFESPAN — Startup + Shutdown
# ══════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle — startup and graceful shutdown."""
    # ── Startup ──
    logger.info("conduit_starting", version="1.0.0", env=settings.ENVIRONMENT)

    await init_redis()
    logger.info("redis_connected")

    await init_db()
    logger.info("database_ready")

    logger.info("conduit_ready", docs_url="/api/docs")

    yield

    # ── Shutdown ──
    logger.info("conduit_shutting_down")
    await close_redis()
    await engine.dispose()
    logger.info("conduit_stopped")


# ══════════════════════════════════════
# APPLICATION FACTORY
# ══════════════════════════════════════

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Conduit API",
        description="MEP Intelligence. Connected. — Bliss Systems LLC",
        version="1.0.0",
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── CORS ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "X-Organization-ID"],
        expose_headers=["X-Organization-ID"],
    )

    # ── Error Handlers ──
    register_error_handlers(app)

    # ── Routers ──
    app.include_router(
        auth_router,
        prefix="/api/v1",
        tags=["Auth & Organizations"],
    )
    app.include_router(
        projects_router,
        prefix="/api/v1",
    )

    # ── Health Check ──
    @app.get("/health", tags=["System"])
    async def health_check() -> dict:
        """
        Health check for Docker + load balancer.
        Returns 200 when application is ready.
        """
        return {
            "status": "healthy",
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
        }

    return app


app = create_app()
