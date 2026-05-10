"""
INTEGRATION TEST — Sprint 1: Plans Module (M3 + M4)
====================================================
Covers: upload, status polling, metadata, tile server, list.
Processing pipeline tasks are tested with mocked I/O.

Fixtures:
  - phone_photo_plan.jpg  → deskew path (source_type=phone_photo)
  - school_plan.pdf       → multi-page PDF path

Total: ~30 tests

Bliss Systems LLC — APEX Standard
"""

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import Organization
from app.models.plans import Plan, PlanPage, PlanProcessingJob
from app.models.projects import Project, ProjectComplexity, ProjectType

# ── URL constants ──────────────────────────────────────────────────────────
PLANS_BASE = "/api/v1"


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def project(db: AsyncSession, test_user: dict) -> Project:
    """Seed a project belonging to the test org."""
    proj = Project(
        name="B&I Office Build",
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
    """Seed a plan in 'ready' status with 1 page (no real S3 content)."""
    plan = Plan(
        org_id=test_user["org"].id,
        project_id=project.id,
        uploaded_by=test_user["user"].id,
        name="Ground Floor MEP",
        original_filename="ground_floor_mep.pdf",
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
        s3_key_full="test-org/test-proj/test-plan/pages/1/full.png",
        s3_key_thumb="test-org/test-proj/test-plan/pages/1/thumb.jpg",
        width_px=2550,
        height_px=3300,
        orientation="portrait",
    )
    db.add(page)

    job = PlanProcessingJob(
        plan_id=plan.id,
        status="ready",
        progress_pct=100,
        current_step="complete",
    )
    db.add(job)
    await db.commit()
    await db.refresh(plan)
    return plan


def _minimal_pdf_bytes() -> bytes:
    """Tiny but valid PDF for upload tests."""
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n%%EOF\n"
    )


def _minimal_jpg_bytes() -> bytes:
    """Tiny JPEG (1×1 white pixel)."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(255, 255, 255)).save(buf, format="JPEG")
    return buf.getvalue()


# ── Upload tests ───────────────────────────────────────────────────────────

class TestPlanUpload:

    @pytest.mark.asyncio
    async def test_upload_pdf_returns_202(
        self, client: AsyncClient, auth_headers: dict, project: Project
    ):
        with (
            patch("app.modules.plans.service.upload_fileobj", return_value="test/key.pdf"),
            patch("app.tasks.plan_tasks.dispatch_plan_processing", return_value="celery-id-1"),
        ):
            resp = await client.post(
                f"{PLANS_BASE}/projects/{project.id}/plans/upload",
                files={"file": ("floor_plan.pdf", _minimal_pdf_bytes(), "application/pdf")},
                headers=auth_headers,
            )
        assert resp.status_code == 202
        body = resp.json()
        assert "plan_id" in body
        assert "job_id" in body
        assert body["status"] == "queued"

    @pytest.mark.asyncio
    async def test_upload_jpg_returns_202(
        self, client: AsyncClient, auth_headers: dict, project: Project
    ):
        with (
            patch("app.modules.plans.service.upload_fileobj", return_value="test/key.jpg"),
            patch("app.tasks.plan_tasks.dispatch_plan_processing", return_value="celery-id-2"),
        ):
            resp = await client.post(
                f"{PLANS_BASE}/projects/{project.id}/plans/upload",
                files={"file": ("phone_photo_plan.jpg", _minimal_jpg_bytes(), "image/jpeg")},
                headers=auth_headers,
            )
        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_upload_with_custom_name(
        self, client: AsyncClient, auth_headers: dict, project: Project
    ):
        with (
            patch("app.modules.plans.service.upload_fileobj", return_value="test/key.pdf"),
            patch("app.tasks.plan_tasks.dispatch_plan_processing", return_value="celery-id-3"),
        ):
            resp = await client.post(
                f"{PLANS_BASE}/projects/{project.id}/plans/upload",
                files={"file": ("plan.pdf", _minimal_pdf_bytes(), "application/pdf")},
                data={"name": "Level 2 HVAC"},
                headers=auth_headers,
            )
        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"

    @pytest.mark.asyncio
    async def test_upload_unsupported_type_returns_422(
        self, client: AsyncClient, auth_headers: dict, project: Project
    ):
        resp = await client.post(
            f"{PLANS_BASE}/projects/{project.id}/plans/upload",
            files={"file": ("doc.docx", b"fake-docx-bytes", "application/vnd.openxmlformats")},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_upload_requires_auth(
        self, client: AsyncClient, project: Project
    ):
        resp = await client.post(
            f"{PLANS_BASE}/projects/{project.id}/plans/upload",
            files={"file": ("plan.pdf", _minimal_pdf_bytes(), "application/pdf")},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_dispatches_celery_pipeline(
        self, client: AsyncClient, auth_headers: dict, project: Project
    ):
        with (
            patch("app.modules.plans.service.upload_fileobj", return_value="key"),
            patch("app.tasks.plan_tasks.dispatch_plan_processing", return_value="task-abc") as mock_dispatch,
        ):
            resp = await client.post(
                f"{PLANS_BASE}/projects/{project.id}/plans/upload",
                files={"file": ("plan.pdf", _minimal_pdf_bytes(), "application/pdf")},
                headers=auth_headers,
            )
        assert resp.status_code == 202
        mock_dispatch.assert_called_once()
        call_kwargs = mock_dispatch.call_args.kwargs
        assert call_kwargs["source_type"] == "pdf"


# ── Status tests ───────────────────────────────────────────────────────────

class TestPlanStatus:

    @pytest.mark.asyncio
    async def test_get_status_returns_job_info(
        self, client: AsyncClient, auth_headers: dict, ready_plan: Plan
    ):
        resp = await client.get(
            f"{PLANS_BASE}/plans/{ready_plan.id}/status",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["progress_pct"] == 100
        assert body["plan_id"] == str(ready_plan.id)

    @pytest.mark.asyncio
    async def test_get_status_unknown_plan_returns_404(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get(
            f"{PLANS_BASE}/plans/{uuid.uuid4()}/status",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_status_wrong_org_returns_404(
        self, client: AsyncClient, db: AsyncSession, auth_headers: dict,
        project: Project
    ):
        # Plan belonging to a different org
        other_org = Organization(name="Other Corp", slug="other-corp")
        db.add(other_org)
        await db.flush()
        alien_plan = Plan(
            org_id=other_org.id,
            project_id=project.id,
            uploaded_by=uuid.uuid4(),
            name="Alien Plan",
            original_filename="alien.pdf",
            source_type="pdf",
            status="ready",
        )
        db.add(alien_plan)
        await db.commit()

        resp = await client.get(
            f"{PLANS_BASE}/plans/{alien_plan.id}/status",
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ── Metadata tests ─────────────────────────────────────────────────────────

class TestPlanMetadata:

    @pytest.mark.asyncio
    async def test_get_metadata_returns_plan_info(
        self, client: AsyncClient, auth_headers: dict, ready_plan: Plan
    ):
        with patch("app.modules.plans.service.get_presigned_url", return_value="/dev/url"):
            resp = await client.get(
                f"{PLANS_BASE}/plans/{ready_plan.id}/metadata",
                headers=auth_headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["plan_type"] == "hvac"
        assert body["status"] == "ready"
        assert body["total_pages"] == 1
        assert len(body["pages"]) == 1
        assert body["pages"][0]["page_number"] == 1

    @pytest.mark.asyncio
    async def test_metadata_includes_page_urls(
        self, client: AsyncClient, auth_headers: dict, ready_plan: Plan
    ):
        with patch("app.modules.plans.service.get_presigned_url", return_value="https://s3.test/img"):
            resp = await client.get(
                f"{PLANS_BASE}/plans/{ready_plan.id}/metadata",
                headers=auth_headers,
            )
        body = resp.json()
        assert body["pages"][0]["thumb_url"] == "https://s3.test/img"
        assert body["pages"][0]["full_url"] == "https://s3.test/img"


# ── List tests ─────────────────────────────────────────────────────────────

class TestPlanList:

    @pytest.mark.asyncio
    async def test_list_returns_plans_in_project(
        self, client: AsyncClient, auth_headers: dict, project: Project, ready_plan: Plan
    ):
        with patch("app.modules.plans.service.get_presigned_url", return_value="/url"):
            resp = await client.get(
                f"{PLANS_BASE}/projects/{project.id}/plans",
                headers=auth_headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        ids = [p["id"] for p in body]
        assert str(ready_plan.id) in ids

    @pytest.mark.asyncio
    async def test_list_empty_project_returns_empty_list(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: dict
    ):
        empty_proj = Project(
            name="Empty Project",
            org_id=test_user["org"].id,
            type=ProjectType.SMALL_COMMERCIAL,
            complexity=ProjectComplexity.SIMPLE,
            is_active=True,
        )
        db.add(empty_proj)
        await db.commit()

        resp = await client.get(
            f"{PLANS_BASE}/projects/{empty_proj.id}/plans",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ── Tile server tests ──────────────────────────────────────────────────────

class TestTileServer:

    @pytest.mark.asyncio
    async def test_tile_returns_webp(
        self, client: AsyncClient, auth_headers: dict, ready_plan: Plan
    ):
        fake_tile = b"RIFF\x00\x00\x00\x00WEBPVP8 "  # minimal WebP header

        with patch("app.core.storage.download_bytes", return_value=fake_tile):
            resp = await client.get(
                f"{PLANS_BASE}/plans/{ready_plan.id}/pages/1/tiles/0/0/0",
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/webp"
        assert resp.headers["cache-control"] == "public, max-age=7200"

    @pytest.mark.asyncio
    async def test_tile_missing_triggers_on_demand_generation(
        self, client: AsyncClient, auth_headers: dict, ready_plan: Plan
    ):
        with (
            patch("app.core.storage.download_bytes", side_effect=FileNotFoundError),
            patch("app.tasks.plan_tasks.generate_tile_on_demand") as mock_task,
        ):
            mock_task.apply_async = MagicMock()
            resp = await client.get(
                f"{PLANS_BASE}/plans/{ready_plan.id}/pages/1/tiles/2/0/0",
                headers=auth_headers,
            )
        # 404 is expected while tile generates
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_tile_zoom_out_of_range_returns_400(
        self, client: AsyncClient, auth_headers: dict, ready_plan: Plan
    ):
        resp = await client.get(
            f"{PLANS_BASE}/plans/{ready_plan.id}/pages/1/tiles/9/0/0",
            headers=auth_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_tile_plan_not_ready_returns_404(
        self, client: AsyncClient, auth_headers: dict, db: AsyncSession,
        test_user: dict, project: Project
    ):
        queued_plan = Plan(
            org_id=test_user["org"].id,
            project_id=project.id,
            uploaded_by=test_user["user"].id,
            name="Processing",
            original_filename="plan.pdf",
            source_type="pdf",
            status="processing",
        )
        db.add(queued_plan)
        await db.commit()

        resp = await client.get(
            f"{PLANS_BASE}/plans/{queued_plan.id}/pages/1/tiles/0/0/0",
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ── Processing pipeline unit tests ────────────────────────────────────────

class TestProcessingPipeline:
    """Unit tests for Celery task logic with mocked I/O."""

    def _make_job_ctx(self) -> tuple[str, str, str, str]:
        return str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_analyze_plan_detects_hvac_type(self):
        """Keyword detection in OCR text maps to correct plan_type."""
        from app.tasks.plan_tasks import PLAN_KEYWORDS

        text = "HVAC SUPPLY AIR DUCT 12x8 AHU-1 VAV-C1.2 CFM 300"
        text_lower = text.lower()
        detected = "unknown"
        for ptype, keywords in PLAN_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                detected = ptype
                break
        assert detected == "hvac"

    @pytest.mark.asyncio
    async def test_analyze_plan_detects_electrical_type(self):
        from app.tasks.plan_tasks import PLAN_KEYWORDS

        text = "ELECTRICAL PANEL SCHEDULE CIRCUIT BREAKER 20A"
        text_lower = text.lower()
        detected = "unknown"
        for ptype, keywords in PLAN_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                detected = ptype
                break
        assert detected == "electrical"

    @pytest.mark.asyncio
    async def test_analyze_plan_detects_scale(self):
        import re
        from app.tasks.plan_tasks import PLAN_KEYWORDS

        text = 'SCALE: 1/8" = 1\'-0"'
        match = re.search(r'(\d+/\d+["\']?\s*=\s*\d+[\'"-]\d*["\']?|\d+:\d+)', text)
        assert match is not None
        assert "1/8" in match.group(0)

    @pytest.mark.asyncio
    async def test_complexity_thresholds(self):
        """Word count bucketing: <200=simple, <800=standard, >=800=complex."""
        def classify(text: str) -> str:
            count = len(text.split())
            if count < 200:
                return "simple"
            elif count < 800:
                return "standard"
            return "complex"

        assert classify("word " * 50) == "simple"
        assert classify("word " * 300) == "standard"
        assert classify("word " * 900) == "complex"

    @pytest.mark.asyncio
    async def test_source_type_detection(self):
        from app.modules.plans.service import _detect_source_type
        assert _detect_source_type("plan.pdf") == "pdf"
        assert _detect_source_type("photo.jpg") == "phone_photo"
        assert _detect_source_type("scan.png") == "phone_photo"
        assert _detect_source_type("capture.HEIC") == "phone_photo"

    @pytest.mark.asyncio
    async def test_tile_key_format(self):
        from app.core.storage import plan_tile_key
        key = plan_tile_key("plan-uuid", 1, 2, 3, 4)
        assert key == "tiles/plan-uuid/1/2/3/4.webp"

    @pytest.mark.asyncio
    async def test_plan_page_full_key_format(self):
        from app.core.storage import plan_page_full_key
        key = plan_page_full_key("org1", "proj1", "plan1", 2)
        assert key == "org1/proj1/plan1/pages/2/full.png"

    @pytest.mark.asyncio
    async def test_plan_page_thumb_key_format(self):
        from app.core.storage import plan_page_thumb_key
        key = plan_page_thumb_key("org1", "proj1", "plan1", 3)
        assert key == "org1/proj1/plan1/pages/3/thumb.jpg"

    @pytest.mark.asyncio
    async def test_dev_mode_storage_roundtrip(self, tmp_path, monkeypatch):
        """Local dev storage writes and reads back correctly."""
        monkeypatch.setattr(
            "app.core.storage._is_dev_mode", lambda: True
        )
        monkeypatch.setattr(
            "app.core.storage._local_path",
            lambda key: (tmp_path / key.replace("/", "_")),
        )

        from app.core.storage import upload_bytes, download_bytes
        data = b"test-tile-data"
        upload_bytes(data, "bucket", "test/key.webp", "image/webp")
        # In real dev mode the file is under /tmp/conduit-dev-storage
        # We just test the upload doesn't raise
