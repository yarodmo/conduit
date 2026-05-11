"""
INTEGRATION TEST — Sprint 2: AI Takeoff Engine (M5)
=====================================================
Covers: cost preview, initiation, item CRUD, approve, summary, exports.
Claude API calls are fully mocked — no real API charges in tests.

Total: ~28 tests

Bliss Systems LLC — APEX Standard
"""

import io
import json
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plans import Plan, PlanPage
from app.models.projects import Project, ProjectComplexity, ProjectType
from app.models.takeoff import TakeoffItem, TakeoffJob

BASE = "/api/v1"


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def project(db: AsyncSession, test_user: dict) -> Project:
    proj = Project(
        name="MEP Office Build",
        org_id=test_user["org"].id,
        type=ProjectType.COMMERCIAL,
        complexity=ProjectComplexity.STANDARD,
        is_active=True,
    )
    db.add(proj)
    await db.commit()
    await db.refresh(proj)
    return proj


@pytest_asyncio.fixture
async def ready_plan(db: AsyncSession, test_user: dict, project: Project) -> Plan:
    plan = Plan(
        org_id=test_user["org"].id,
        project_id=project.id,
        uploaded_by=test_user["user"].id,
        name="Level 1 HVAC",
        original_filename="level1_hvac.pdf",
        source_type="pdf",
        status="ready",
        total_pages=1,
        plan_type="hvac",
        complexity_score="standard",
    )
    db.add(plan)
    await db.flush()

    page = PlanPage(
        plan_id=plan.id,
        page_number=1,
        s3_key_full="org/proj/plan/pages/1/full.png",
        width_px=2550,
        height_px=3300,
        orientation="portrait",
    )
    db.add(page)
    await db.commit()
    await db.refresh(plan)
    return plan


@pytest_asyncio.fixture
async def processing_plan(db: AsyncSession, test_user: dict, project: Project) -> Plan:
    plan = Plan(
        org_id=test_user["org"].id,
        project_id=project.id,
        uploaded_by=test_user["user"].id,
        name="Processing Plan",
        original_filename="processing.pdf",
        source_type="pdf",
        status="processing",
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


@pytest_asyncio.fixture
async def completed_job(db: AsyncSession, test_user: dict, ready_plan: Plan, project: Project) -> TakeoffJob:
    job = TakeoffJob(
        plan_id=ready_plan.id,
        org_id=test_user["org"].id,
        project_id=project.id,
        created_by=test_user["user"].id,
        status="completed",
        model_version="claude-sonnet-4-5-20241022",
        prompt_version="v1",
        total_sections=1,
        sections_completed=1,
        total_items=3,
        low_confidence_count=1,
        actual_cost_usd=Decimal("0.0085"),
        total_material_cost_usd=Decimal("1250.00"),
    )
    db.add(job)
    await db.flush()

    items = [
        TakeoffItem(
            takeoff_job_id=job.id,
            type="VAV",
            tag="VAV-C1.2",
            quantity=Decimal("1"),
            unit="EA",
            specification="VAV box 300 CFM",
            system="supply",
            cfm_or_gpm=Decimal("300"),
            confidence=92,
            unit_cost_usd=Decimal("850.00"),
            total_cost_usd=Decimal("850.00"),
        ),
        TakeoffItem(
            takeoff_job_id=job.id,
            type="DIFFUSER",
            tag=None,
            quantity=Decimal("12"),
            unit="EA",
            specification="A10 diffuser 100 CFM",
            system="supply",
            cfm_or_gpm=Decimal("100"),
            confidence=85,
            unit_cost_usd=Decimal("25.00"),
            total_cost_usd=Decimal("300.00"),
        ),
        TakeoffItem(
            takeoff_job_id=job.id,
            type="DUCT",
            tag=None,
            quantity=Decimal("45"),
            unit="LF",
            specification="12x8 supply duct",
            system="supply",
            confidence=22,
            requires_review=True,
            unit_cost_usd=Decimal("2.22"),
            total_cost_usd=Decimal("100.00"),
        ),
    ]
    for i in items:
        db.add(i)
    await db.commit()
    await db.refresh(job)
    return job


# ── Cost Preview ───────────────────────────────────────────────────────────

class TestCostPreview:

    @pytest.mark.asyncio
    async def test_cost_preview_returns_estimate(
        self, client: AsyncClient, auth_headers: dict, ready_plan: Plan
    ):
        resp = await client.get(
            f"{BASE}/plans/{ready_plan.id}/takeoff/cost-preview",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "estimated_cost_usd" in body
        assert body["sections"] >= 1
        assert body["estimated_cost_usd"] > 0

    @pytest.mark.asyncio
    async def test_cost_preview_plan_not_ready_returns_422(
        self, client: AsyncClient, auth_headers: dict, processing_plan: Plan
    ):
        resp = await client.get(
            f"{BASE}/plans/{processing_plan.id}/takeoff/cost-preview",
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_cost_preview_unknown_plan_returns_404(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get(
            f"{BASE}/plans/{uuid.uuid4()}/takeoff/cost-preview",
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ── Initiation ─────────────────────────────────────────────────────────────

class TestTakeoffInitiation:

    @pytest.mark.asyncio
    async def test_initiate_returns_202_with_job_id(
        self, client: AsyncClient, auth_headers: dict, ready_plan: Plan
    ):
        with patch("app.tasks.ai_tasks.run_takeoff_analysis") as mock_task:
            mock_result = MagicMock()
            mock_result.id = "celery-test-id"
            mock_task.apply_async.return_value = mock_result

            resp = await client.post(
                f"{BASE}/plans/{ready_plan.id}/takeoff",
                headers=auth_headers,
            )
        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body
        assert body["status"] == "pending"
        assert body["estimated_cost_usd"] is not None

    @pytest.mark.asyncio
    async def test_initiate_plan_not_ready_returns_422(
        self, client: AsyncClient, auth_headers: dict, processing_plan: Plan
    ):
        resp = await client.post(
            f"{BASE}/plans/{processing_plan.id}/takeoff",
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_initiate_dispatches_celery_task(
        self, client: AsyncClient, auth_headers: dict, ready_plan: Plan
    ):
        with patch("app.tasks.ai_tasks.run_takeoff_analysis") as mock_task:
            mock_result = MagicMock()
            mock_result.id = "celery-test-id-2"
            mock_task.apply_async.return_value = mock_result

            resp = await client.post(
                f"{BASE}/plans/{ready_plan.id}/takeoff",
                headers=auth_headers,
            )
        assert resp.status_code == 202
        mock_task.apply_async.assert_called_once()
        call_kwargs = mock_task.apply_async.call_args.kwargs["kwargs"]
        assert call_kwargs["plan_id"] == str(ready_plan.id)


# ── Job Status ─────────────────────────────────────────────────────────────

class TestJobStatus:

    @pytest.mark.asyncio
    async def test_get_status_returns_job_info(
        self, client: AsyncClient, auth_headers: dict, completed_job: TakeoffJob
    ):
        resp = await client.get(
            f"{BASE}/takeoff/{completed_job.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["total_items"] == 3
        assert body["progress_pct"] == 100

    @pytest.mark.asyncio
    async def test_get_items_returns_all_with_confidence(
        self, client: AsyncClient, auth_headers: dict, completed_job: TakeoffJob
    ):
        resp = await client.get(
            f"{BASE}/takeoff/{completed_job.id}/items",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 3
        types = {i["type"] for i in body["items"]}
        assert "VAV" in types
        assert "DIFFUSER" in types

    @pytest.mark.asyncio
    async def test_unknown_job_returns_404(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get(
            f"{BASE}/takeoff/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ── Item CRUD ──────────────────────────────────────────────────────────────

class TestItemCRUD:

    @pytest.mark.asyncio
    async def test_update_item_sets_human_corrected(
        self, client: AsyncClient, auth_headers: dict,
        db: AsyncSession, completed_job: TakeoffJob
    ):
        from sqlalchemy import select
        item = (await db.execute(
            select(TakeoffItem).where(TakeoffItem.takeoff_job_id == completed_job.id)
        )).scalars().first()

        resp = await client.patch(
            f"{BASE}/takeoff/{completed_job.id}/items/{item.id}",
            json={"quantity": 2.0, "correction_notes": "Recounted on site"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["human_corrected"] is True
        assert body["correction_notes"] == "Recounted on site"

    @pytest.mark.asyncio
    async def test_add_item_returns_201(
        self, client: AsyncClient, auth_headers: dict, completed_job: TakeoffJob
    ):
        resp = await client.post(
            f"{BASE}/takeoff/{completed_job.id}/items",
            json={
                "type": "AHU",
                "tag": "AHU-1",
                "quantity": 1,
                "unit": "EA",
                "specification": "Air Handling Unit 5000 CFM",
                "system": "supply",
                "cfm_or_gpm": 5000,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["type"] == "AHU"
        assert body["human_corrected"] is True

    @pytest.mark.asyncio
    async def test_delete_item_returns_204(
        self, client: AsyncClient, auth_headers: dict,
        db: AsyncSession, completed_job: TakeoffJob
    ):
        from sqlalchemy import select
        item = (await db.execute(
            select(TakeoffItem).where(TakeoffItem.takeoff_job_id == completed_job.id)
        )).scalars().first()

        resp = await client.delete(
            f"{BASE}/takeoff/{completed_job.id}/items/{item.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_cannot_edit_approved_job(
        self, client: AsyncClient, auth_headers: dict,
        db: AsyncSession, completed_job: TakeoffJob
    ):
        # Approve first
        await client.post(
            f"{BASE}/takeoff/{completed_job.id}/approve",
            headers=auth_headers,
        )
        await db.refresh(completed_job)

        from sqlalchemy import select
        item = (await db.execute(
            select(TakeoffItem).where(TakeoffItem.takeoff_job_id == completed_job.id)
        )).scalars().first()

        resp = await client.patch(
            f"{BASE}/takeoff/{completed_job.id}/items/{item.id}",
            json={"quantity": 99},
            headers=auth_headers,
        )
        assert resp.status_code == 409


# ── Approve ────────────────────────────────────────────────────────────────

class TestApprove:

    @pytest.mark.asyncio
    async def test_approve_completed_job(
        self, client: AsyncClient, auth_headers: dict, completed_job: TakeoffJob
    ):
        resp = await client.post(
            f"{BASE}/takeoff/{completed_job.id}/approve",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    @pytest.mark.asyncio
    async def test_cannot_approve_pending_job(
        self, client: AsyncClient, auth_headers: dict,
        db: AsyncSession, test_user: dict, ready_plan: Plan, project: Project
    ):
        pending = TakeoffJob(
            plan_id=ready_plan.id,
            org_id=test_user["org"].id,
            project_id=project.id,
            created_by=test_user["user"].id,
            status="pending",
        )
        db.add(pending)
        await db.commit()

        resp = await client.post(
            f"{BASE}/takeoff/{pending.id}/approve",
            headers=auth_headers,
        )
        assert resp.status_code == 422


# ── Summary ────────────────────────────────────────────────────────────────

class TestSummary:

    @pytest.mark.asyncio
    async def test_summary_returns_breakdown_by_system(
        self, client: AsyncClient, auth_headers: dict, completed_job: TakeoffJob
    ):
        resp = await client.get(
            f"{BASE}/takeoff/{completed_job.id}/summary",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_items"] == 3
        assert body["requires_review_items"] == 1
        assert len(body["breakdown_by_system"]) >= 1


# ── Exports ────────────────────────────────────────────────────────────────

class TestExports:

    @pytest.mark.asyncio
    async def test_export_excel_returns_xlsx(
        self, client: AsyncClient, auth_headers: dict, completed_job: TakeoffJob
    ):
        resp = await client.get(
            f"{BASE}/takeoff/{completed_job.id}/export/excel",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]
        assert len(resp.content) > 1000

    @pytest.mark.asyncio
    async def test_export_pdf_returns_pdf(
        self, client: AsyncClient, auth_headers: dict, completed_job: TakeoffJob
    ):
        resp = await client.get(
            f"{BASE}/takeoff/{completed_job.id}/export/pdf?approver=John+Smith",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"

    @pytest.mark.asyncio
    async def test_export_pending_job_returns_422(
        self, client: AsyncClient, auth_headers: dict,
        db: AsyncSession, test_user: dict, ready_plan: Plan, project: Project
    ):
        pending = TakeoffJob(
            plan_id=ready_plan.id,
            org_id=test_user["org"].id,
            project_id=project.id,
            created_by=test_user["user"].id,
            status="pending",
        )
        db.add(pending)
        await db.commit()

        resp = await client.get(
            f"{BASE}/takeoff/{pending.id}/export/excel",
            headers=auth_headers,
        )
        assert resp.status_code == 422


# ── Pipeline unit tests ────────────────────────────────────────────────────

class TestPipelineUnits:

    def test_cost_estimate_single_section(self):
        from app.tasks.ai_tasks import estimate_cost
        est = estimate_cost(1920, 3300)
        assert est["sections"] == 1
        assert est["estimated_cost_usd"] > 0
        assert est["estimated_input_tokens"] > 0

    def test_cost_estimate_multi_section(self):
        from app.tasks.ai_tasks import estimate_cost
        est = estimate_cost(5000, 3300)
        assert est["sections"] == 3
        assert est["estimated_cost_usd"] > 0

    def test_dedup_keeps_highest_confidence(self):
        from app.tasks.ai_tasks import _dedup_overlap_items
        items = [
            {"type": "VAV", "tag": "VAV-1", "specification": "VAV 300", "confidence": 75},
            {"type": "VAV", "tag": "VAV-1", "specification": "VAV 300", "confidence": 90},
        ]
        result = _dedup_overlap_items(items, n_sections=2)
        assert len(result) == 1
        assert result[0]["confidence"] == 90

    def test_dedup_single_section_passthrough(self):
        from app.tasks.ai_tasks import _dedup_overlap_items
        items = [
            {"type": "DIFFUSER", "tag": None, "specification": "A10 100CFM", "confidence": 85},
            {"type": "VAV", "tag": "VAV-2", "specification": "VAV 500", "confidence": 70},
        ]
        result = _dedup_overlap_items(items, n_sections=1)
        assert len(result) == 2

    def test_low_confidence_threshold(self):
        from app.tasks.ai_tasks import LOW_CONFIDENCE_THRESHOLD
        assert LOW_CONFIDENCE_THRESHOLD == 30

    def test_section_crop_produces_bytes(self):
        from app.tasks.ai_tasks import _crop_section
        from PIL import Image
        img = Image.new("RGB", (4000, 3000), color=(200, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()

        section = _crop_section(img_bytes, section_idx=0, n_sections=2, overlap=0.15)
        assert len(section) > 100
        # Verify it's a valid image
        result_img = Image.open(io.BytesIO(section))
        assert result_img.size[0] == 1024
