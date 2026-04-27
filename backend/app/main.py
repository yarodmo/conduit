"""
Conduit Backend — FastAPI Application Entry Point
ADR-000: Python 3.11+ / FastAPI pure end-to-end
Bliss Systems LLC
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown events."""
    # ── Startup ──
    # TODO: Initialize database connection pool
    # TODO: Initialize Redis connection
    # TODO: Verify S3/MinIO connectivity
    # TODO: Load AI prompt templates
    print("⚡ Conduit Backend starting...")
    yield
    # ── Shutdown ──
    # TODO: Close database connections
    # TODO: Close Redis connections
    print("🛑 Conduit Backend shutting down...")


app = FastAPI(
    title="Conduit API",
    description="MEP Intelligence. Connected. — Bliss Systems LLC",
    version="0.1.0",
    docs_url="/docs" if True else None,  # Disable in production
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS (Prompt 0.1 Security) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # TODO: Load from env
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health Check ──
@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for Docker healthcheck and load balancer."""
    return {"status": "healthy", "service": "conduit-backend", "version": "0.1.0"}


# ── API Router Registration ──
# TODO (Sprint 1): Register module routers
# from app.api.v1 import auth, projects, plans, takeoff
# app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
# app.include_router(projects.router, prefix="/api/v1/projects", tags=["Projects"])
# app.include_router(plans.router, prefix="/api/v1/plans", tags=["Plans"])
# app.include_router(takeoff.router, prefix="/api/v1/takeoff", tags=["Takeoff"])
