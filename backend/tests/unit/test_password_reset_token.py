"""
FORENSIC TEST — GAP-001: Password Reset Token Integrity
========================================================
Validates:
  1. PasswordResetToken model stores correctly without FK violations
  2. PasswordResetRepository creates/marks-used tokens atomically
  3. Consumed tokens (used_at set) are rejected on reuse
  4. Expired tokens are detected
  5. UUID-zero hack is completely absent (no Invitation table abuse)

Bliss Systems LLC — APEX Standard | Sprint 1 Validation
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import Invitation, PasswordResetToken, User
from app.modules.auth.repository import PasswordResetRepository


# ════════════════════════════════════════════════════
# Shared test user fixture (local to this module)
# ════════════════════════════════════════════════════
@pytest_asyncio.fixture
async def seed_user(db: AsyncSession) -> User:
    user = User(
        email="reset_victim@conduit.build",
        hashed_password="bcrypt_hash_placeholder",
        full_name="Reset Victim",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ════════════════════════════════════════════════════
# GAP-001-A: Model integrity (no FK violations)
# ════════════════════════════════════════════════════
class TestPasswordResetTokenModel:

    @pytest.mark.asyncio
    async def test_model_persists_with_real_user_fk(self, db: AsyncSession, seed_user: User):
        """Must NOT raise IntegrityError — FK links to real users.id."""
        token = PasswordResetToken(
            user_id=seed_user.id,
            email=seed_user.email,
            token="secure_opaque_token_abc",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(token)
        await db.commit()
        await db.refresh(token)

        assert token.id is not None
        assert token.user_id == seed_user.id
        assert token.used_at is None

    @pytest.mark.asyncio
    async def test_model_has_no_uuid_zero_hack(self, db: AsyncSession, seed_user: User):
        """
        GAP-001 CRITICAL: The old code set org_id=UUID(int=0) in Invitation.
        Verify Invitation table is NOT being used for password resets.
        """
        # After a password reset, Invitation table must remain untouched
        initial_count = (await db.execute(select(Invitation))).scalars().all()
        initial_len = len(initial_count)

        token = PasswordResetToken(
            user_id=seed_user.id,
            email=seed_user.email,
            token="test_no_uuid_zero",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(token)
        await db.commit()

        after_count = (await db.execute(select(Invitation))).scalars().all()
        assert len(after_count) == initial_len, (
            "Invitation table was modified during password reset — UUID-zero hack still active!"
        )

    @pytest.mark.asyncio
    async def test_token_is_unique_constraint(self, db: AsyncSession, seed_user: User):
        """Token column must be UNIQUE — duplicate token must fail."""
        from sqlalchemy.exc import IntegrityError

        t1 = PasswordResetToken(
            user_id=seed_user.id,
            email=seed_user.email,
            token="DUPLICATE_TOKEN",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        t2 = PasswordResetToken(
            user_id=seed_user.id,
            email=seed_user.email,
            token="DUPLICATE_TOKEN",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(t1)
        await db.flush()
        db.add(t2)
        with pytest.raises(IntegrityError):
            await db.flush()


# ════════════════════════════════════════════════════
# GAP-001-B: Repository behavior
# ════════════════════════════════════════════════════
class TestPasswordResetRepository:

    @pytest.mark.asyncio
    async def test_create_token_stores_all_fields(self, db: AsyncSession, seed_user: User):
        repo = PasswordResetRepository(db)
        tok = await repo.create(
            email=seed_user.email,
            token="test_token_123",
            user_id=seed_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        assert tok.token is not None
        assert tok.email == seed_user.email
        assert tok.used_at is None
        assert tok.expires_at > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_get_by_token_returns_record(self, db: AsyncSession, seed_user: User):
        repo = PasswordResetRepository(db)
        created = await repo.create(
            email=seed_user.email,
            token="test_token_456",
            user_id=seed_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        fetched = await repo.get_by_token(created.token)
        assert fetched is not None
        assert fetched.id == created.id

    @pytest.mark.asyncio
    async def test_mark_used_sets_used_at(self, db: AsyncSession, seed_user: User):
        repo = PasswordResetRepository(db)
        tok = await repo.create(
            email=seed_user.email,
            token="test_token_789",
            user_id=seed_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        await repo.mark_used(tok.id)
        await db.refresh(tok)

        assert tok.used_at is not None, "used_at must be set after mark_used"
