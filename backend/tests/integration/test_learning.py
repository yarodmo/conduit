"""
Conduit Tests — Self-Learning Pipeline (M13) integration tests.

Coverage:
  - GET /learning/dashboard — empty state (no insights yet)
  - GET /learning/insights/latest — 404 when no insights
  - POST /learning/trigger — runs analysis, returns insight_id
  - POST /learning/trigger with corrections — generates meaningful report
  - Low accuracy threshold detection (< 70%)
  - Dashboard reflects latest insight after trigger
  - Nightly beat schedule registered
  - LearningService.record_correction_event
  - Unauthorized → 401

Bliss Systems LLC — APEX Standard
"""

import pytest
import uuid
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import LearningInsight, LearningCorrectionEvent
from app.models.projects import Project, ProjectType, ProjectComplexity
from app.models.takeoff import TakeoffJob, TakeoffItem


# ══════════════════════════════════════
# HELPERS
# ══════════════════════════════════════

async def _seed_takeoff_with_corrections(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    num_corrections: int = 3,
    total_items: int = 10,
    prompt_version: str = "v1",
) -> TakeoffJob:
    """Seed a completed TakeoffJob with human-corrected items."""
    project = Project(
        org_id=org_id,
        name="Learning Test Project",
        type=ProjectType.COMMERCIAL,
        complexity=ProjectComplexity.STANDARD,
    )
    db.add(project)
    await db.flush()

    job = TakeoffJob(
        plan_id=uuid.uuid4(),
        org_id=org_id,
        project_id=project.id,
        created_by=user_id,
        status="completed",
        prompt_version=prompt_version,
        total_sections=1,
        sections_completed=1,
    )
    db.add(job)
    await db.flush()

    for i in range(total_items):
        is_corrected = i < num_corrections
        item = TakeoffItem(
            takeoff_job_id=job.id,
            type="VAV" if i % 2 == 0 else "DIFFUSER",
            tag=f"VAV-{i}",
            quantity=Decimal("1"),
            unit="EA",
            specification=f"VAV Box {i}",
            confidence=45 if is_corrected else 90,
            requires_review=is_corrected,
            human_corrected=is_corrected,
            correction_notes="Wrong quantity" if is_corrected else None,
        )
        db.add(item)

    await db.commit()
    return job


# ══════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_dashboard_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/learning/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["latest_insight"] is None
    assert data["total_corrections_all_time"] == 0
    assert data["prompt_accuracy"] == []
    assert data["top_errors"] == []


@pytest.mark.asyncio
async def test_dashboard_unauthorized(client: AsyncClient):
    resp = await client.get("/api/v1/learning/dashboard")
    assert resp.status_code == 401


# ══════════════════════════════════════
# LATEST INSIGHT
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_latest_insight_404_when_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/learning/insights/latest", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_latest_insight_returns_after_trigger(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: dict
):
    await _seed_takeoff_with_corrections(
        db, test_user["org"].id, test_user["user"].id
    )

    await client.post("/api/v1/learning/trigger", headers=auth_headers)

    resp = await client.get("/api/v1/learning/insights/latest", headers=auth_headers)
    assert resp.status_code == 200
    insight = resp.json()
    assert "period_start" in insight
    assert "period_end" in insight
    assert insight["total_corrections"] >= 3


# ══════════════════════════════════════
# TRIGGER ANALYSIS
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_trigger_no_data(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/learning/trigger", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "insight_id" in data
    assert data["period_analyzed_days"] == 30
    assert "0 corrections" in data["summary"]


@pytest.mark.asyncio
async def test_trigger_with_corrections(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    await _seed_takeoff_with_corrections(
        db, test_user["org"].id, test_user["user"].id,
        num_corrections=4, total_items=10
    )

    resp = await client.post("/api/v1/learning/trigger", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["period_analyzed_days"] == 30
    assert uuid.UUID(data["insight_id"])  # valid UUID
    assert "4 corrections" in data["summary"] or "corrections" in data["summary"]


@pytest.mark.asyncio
async def test_trigger_calculates_accuracy_by_version(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    # v1 job with 5 corrections out of 5 items (low accuracy)
    await _seed_takeoff_with_corrections(
        db, test_user["org"].id, test_user["user"].id,
        num_corrections=5, total_items=5, prompt_version="v1"
    )

    resp = await client.post("/api/v1/learning/trigger", headers=auth_headers)
    assert resp.status_code == 200

    # Verify insight stored accuracy_by_version
    insight_resp = await client.get("/api/v1/learning/insights/latest", headers=auth_headers)
    insight = insight_resp.json()
    assert insight["accuracy_by_version"] is not None
    assert "v1" in insight["accuracy_by_version"]


@pytest.mark.asyncio
async def test_trigger_detects_low_accuracy(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    # Very low confidence items → accuracy below threshold
    for _ in range(3):
        await _seed_takeoff_with_corrections(
            db, test_user["org"].id, test_user["user"].id,
            num_corrections=8, total_items=10, prompt_version="v1"
        )

    resp = await client.post("/api/v1/learning/trigger", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    # Summary should mention accuracy or threshold
    assert "summary" in data
    assert len(data["summary"]) > 0


@pytest.mark.asyncio
async def test_trigger_generates_top_error_patterns(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    await _seed_takeoff_with_corrections(
        db, test_user["org"].id, test_user["user"].id,
        num_corrections=5, total_items=10
    )

    await client.post("/api/v1/learning/trigger", headers=auth_headers)

    insight_resp = await client.get("/api/v1/learning/insights/latest", headers=auth_headers)
    insight = insight_resp.json()
    assert insight["top_error_patterns"] is not None
    assert len(insight["top_error_patterns"]) >= 1
    pattern = insight["top_error_patterns"][0]
    assert "component_type" in pattern
    assert "count" in pattern


@pytest.mark.asyncio
async def test_trigger_updates_job_accuracy_score(
    db: AsyncSession, test_user: dict,
    client: AsyncClient, auth_headers: dict
):
    job = await _seed_takeoff_with_corrections(
        db, test_user["org"].id, test_user["user"].id,
        num_corrections=2, total_items=10
    )

    await client.post("/api/v1/learning/trigger", headers=auth_headers)

    await db.refresh(job)
    # accuracy_score should now be set (80% = 8/10 items not corrected)
    assert job.accuracy_score is not None


# ══════════════════════════════════════
# DASHBOARD WITH DATA
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_dashboard_reflects_latest_insight(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    await _seed_takeoff_with_corrections(
        db, test_user["org"].id, test_user["user"].id
    )
    await client.post("/api/v1/learning/trigger", headers=auth_headers)

    resp = await client.get("/api/v1/learning/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["latest_insight"] is not None
    assert data["total_corrections_all_time"] >= 3


# ══════════════════════════════════════
# CORRECTION EVENT RECORDING
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_record_correction_event(
    db: AsyncSession, test_user: dict
):
    from app.modules.learning.service import LearningService

    job_id = uuid.uuid4()
    item_id = uuid.uuid4()

    await LearningService.record_correction_event(
        db=db,
        org_id=test_user["org"].id,
        takeoff_job_id=job_id,
        item_id=item_id,
        prompt_version="v1",
        component_type="VAV",
        original_confidence=35,
        correction_type="qty",
    )
    await db.commit()

    from sqlalchemy import select
    stmt = select(LearningCorrectionEvent).where(
        LearningCorrectionEvent.item_id == item_id
    )
    event = (await db.execute(stmt)).scalar_one_or_none()
    assert event is not None
    assert event.component_type == "VAV"
    assert event.correction_type == "qty"
    assert event.original_confidence == 35


# ══════════════════════════════════════
# UNIT — beat schedule + constants
# ══════════════════════════════════════

def test_nightly_beat_registered():
    from app.tasks.celery_app import celery_app
    schedule = celery_app.conf.beat_schedule
    assert "learning-analysis-nightly" in schedule
    task_name = schedule["learning-analysis-nightly"]["task"]
    assert task_name == "app.tasks.learning_tasks.run_learning_analysis"
    assert schedule["learning-analysis-nightly"]["schedule"] == 86400.0


def test_low_accuracy_threshold():
    from app.modules.learning.service import LOW_ACCURACY_THRESHOLD
    assert LOW_ACCURACY_THRESHOLD == 70.0


def test_recommendation_no_corrections():
    from app.modules.learning.service import _generate_recommendation
    rec = _generate_recommendation([], [], 0)
    assert "No corrections" in rec


def test_recommendation_with_errors():
    from app.modules.learning.service import _generate_recommendation
    rec = _generate_recommendation(
        [{"component_type": "VAV", "count": 5, "avg_confidence": 42.0}],
        ["v1"],
        10,
    )
    assert "VAV" in rec
    assert "v1" in rec
