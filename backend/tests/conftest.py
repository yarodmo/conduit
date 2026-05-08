"""
Conduit Tests — conftest.py
Shared fixtures for all test modules.

Strategy:
- SQLite in-memory via aiosqlite (fast, no Docker needed)
- fakeredis for Redis isolation
- TestClient via httpx + ASGITransport
- Per-test DB isolation via rollback

Bliss Systems LLC — APEX Standard
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.main import create_app
from app.models import *  # noqa: F401, F403  — trigger all model registration
from app.models.auth import OrgRole, Organization, OrganizationMember, SubscriptionPlan, User
from app.models.base import AuditBase, ConduitBase


# ══════════════════════════════════════
# DATABASE FIXTURE — SQLite in-memory
# ══════════════════════════════════════

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def engine():
    """Create fresh in-memory SQLite engine per test."""
    eng = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    async with eng.begin() as conn:
        await conn.run_sync(ConduitBase.metadata.create_all)
        await conn.run_sync(AuditBase.metadata.create_all)

    yield eng

    async with eng.begin() as conn:
        await conn.run_sync(AuditBase.metadata.drop_all)
        await conn.run_sync(ConduitBase.metadata.drop_all)

    await eng.dispose()


@pytest_asyncio.fixture(scope="function")
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async DB session, rolled back after each test."""
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session
        await session.rollback()


# ══════════════════════════════════════
# REDIS FIXTURE — fakeredis
# ══════════════════════════════════════

@pytest_asyncio.fixture(scope="function")
async def fake_redis() -> AsyncGenerator[FakeRedis, None]:
    """In-memory Redis instance, fully isolated per test."""
    client = FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


# ══════════════════════════════════════
# APP FIXTURE — full ASGI app
# ══════════════════════════════════════

@pytest_asyncio.fixture(scope="function")
async def app(db: AsyncSession, fake_redis: FakeRedis):
    """Create test app with DB + Redis overrides."""
    from app.core.database import get_db
    import app.core.redis as redis_module

    application = create_app()

    # Override DB dependency
    async def override_get_db():
        yield db

    application.dependency_overrides[get_db] = override_get_db

    # Patch redis module
    redis_module.redis_client = fake_redis

    yield application

    application.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ══════════════════════════════════════
# DATA FIXTURES — reusable entities
# ══════════════════════════════════════

@pytest_asyncio.fixture
async def free_plan(db: AsyncSession) -> SubscriptionPlan:
    """Seed a free subscription plan."""
    plan = SubscriptionPlan(
        name="free",
        display_name="Free",
        price_monthly_usd=0,
        price_annual_usd=0,
        limits={
            "max_projects": 3,
            "max_pages": 50,
            "max_ai_takeoffs_per_month": 5,
            "max_users": 5,
        },
        is_active=True,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


@pytest_asyncio.fixture
async def test_user(db: AsyncSession, free_plan: SubscriptionPlan) -> dict[str, Any]:
    """
    Create a test user + org + membership.
    Returns dict with user, org, membership, and raw credentials.
    """
    user = User(
        email="test@conduit.build",
        hashed_password=hash_password("Test1234!"),
        full_name="Test Engineer",
        is_active=True,
    )
    db.add(user)
    await db.flush()

    org = Organization(
        name="Test Engineering Co",
        slug="test-engineering-co",
        plan_id=free_plan.id,
    )
    db.add(org)
    await db.flush()

    membership = OrganizationMember(
        user_id=user.id,
        org_id=org.id,
        role=OrgRole.ORG_ADMIN,
    )
    db.add(membership)
    await db.commit()

    return {
        "user": user,
        "org": org,
        "membership": membership,
        "email": "test@conduit.build",
        "password": "Test1234!",
        "org_id": str(org.id),
    }


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, test_user: dict, free_plan: SubscriptionPlan) -> dict[str, str]:
    """
    Login and return auth headers with access token + org ID.
    Ready to use in endpoint tests.
    """
    response = await client.post("/api/v1/login", json={
        "email": test_user["email"],
        "password": test_user["password"],
    })
    assert response.status_code == 200, f"Auth fixture login failed: {response.json()}"
    tokens = response.json()

    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "X-Organization-ID": test_user["org_id"],
        "refresh_token": tokens["refresh_token"],
    }


# ══════════════════════════════════════
# HELPERS
# ══════════════════════════════════════

def make_register_payload(
    email: str = "new@conduit.build",
    password: str = "NewPass123!",
    full_name: str = "New Engineer",
    org_name: str = "New Org LLC",
) -> dict:
    """Generate a valid registration payload."""
    return {
        "email": email,
        "password": password,
        "full_name": full_name,
        "org_name": org_name,
    }
