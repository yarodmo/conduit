"""
Conduit Tests — Reports & Exports (M9) integration tests.

Coverage:
  - Create report job for each type → 202 Accepted, status=queued
  - GET job status polling
  - Job not found (wrong org) → 404
  - Unauthorized → 401
  - ReportType enum coverage

Bliss Systems LLC — APEX Standard
"""

import pytest
import uuid
from unittest.mock import patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reports import ReportJob, ReportStatus, ReportType

# Celery tasks won't run in test env — the service's try/except absorbs the failure.
# Creation tests just verify 202 + queued status.


# ══════════════════════════════════════
# HELPERS
# ══════════════════════════════════════

async def _create_job(client: AsyncClient, auth_headers: dict,
                       endpoint: str) -> dict:
    resp = await client.post(endpoint, headers=auth_headers)
    assert resp.status_code == 202, resp.json()
    return resp.json()


def _fake_entity() -> str:
    return str(uuid.uuid4())


# ══════════════════════════════════════
# JOB CREATION — all report types
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_create_takeoff_excel_job(client: AsyncClient, auth_headers: dict):
    entity_id = _fake_entity()
    resp = await client.post(
        f"/api/v1/reports/takeoff/{entity_id}/export/excel",
        headers=auth_headers,
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["report_type"] == "takeoff_excel"
    assert data["entity_id"] == entity_id
    assert data["download_url"] is None


@pytest.mark.asyncio
async def test_create_takeoff_pdf_job(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/v1/reports/takeoff/{_fake_entity()}/export/pdf",
        headers=auth_headers,
    )
    assert resp.status_code == 202
    assert resp.json()["report_type"] == "takeoff_pdf"


@pytest.mark.asyncio
async def test_create_project_progress_job(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/v1/reports/project/{_fake_entity()}/progress-pdf",
        headers=auth_headers,
    )
    assert resp.status_code == 202
    assert resp.json()["report_type"] == "project_progress"


@pytest.mark.asyncio
async def test_create_rfi_pdf_job(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/v1/reports/rfi/{_fake_entity()}/export/pdf",
        headers=auth_headers,
    )
    assert resp.status_code == 202
    assert resp.json()["report_type"] == "rfi_pdf"


@pytest.mark.asyncio
async def test_create_change_order_pdf_job(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/v1/reports/change-order/{_fake_entity()}/export/pdf",
        headers=auth_headers,
    )
    assert resp.status_code == 202
    assert resp.json()["report_type"] == "change_order_pdf"


# ══════════════════════════════════════
# JOB STATUS POLLING
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_get_job_queued(client: AsyncClient, auth_headers: dict):
    entity_id = _fake_entity()
    create_resp = await client.post(
        f"/api/v1/reports/takeoff/{entity_id}/export/excel",
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/reports/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == job_id
    assert data["status"] == "queued"
    assert data["download_url"] is None


@pytest.mark.asyncio
async def test_get_job_completed_has_download_url(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    # Seed a completed job directly
    job = ReportJob(
        org_id=test_user["org"].id,
        created_by=test_user["user"].id,
        report_type="takeoff_excel",
        entity_id=uuid.uuid4(),
        status="completed",
        s3_key="reports/org/job/takeoff_JOB-001.xlsx",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    with patch("app.modules.reports.service.get_presigned_url",
               return_value="https://s3.example.com/signed-url"):
        resp = await client.get(f"/api/v1/reports/jobs/{job.id}", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["download_url"] == "https://s3.example.com/signed-url"


@pytest.mark.asyncio
async def test_get_job_failed_has_error(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    job = ReportJob(
        org_id=test_user["org"].id,
        created_by=test_user["user"].id,
        report_type="rfi_pdf",
        entity_id=uuid.uuid4(),
        status="failed",
        error_message="RFI not found in database",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    resp = await client.get(f"/api/v1/reports/jobs/{job.id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["error_message"] == "RFI not found in database"
    assert data["download_url"] is None


# ══════════════════════════════════════
# SECURITY / ISOLATION
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_get_job_wrong_org_returns_404(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession
):
    # Job belongs to a different org
    job = ReportJob(
        org_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        report_type="takeoff_excel",
        entity_id=uuid.uuid4(),
        status="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    resp = await client.get(f"/api/v1/reports/jobs/{job.id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_job_returns_404(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/v1/reports/jobs/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unauthorized_returns_401(client: AsyncClient):
    resp = await client.post(f"/api/v1/reports/takeoff/{uuid.uuid4()}/export/excel")
    assert resp.status_code == 401


# ══════════════════════════════════════
# UNIT — ReportType enum completeness
# ══════════════════════════════════════

def test_all_report_types_defined():
    expected = {
        "takeoff_excel", "takeoff_pdf", "project_progress",
        "rfi_pdf", "change_order_pdf",
    }
    actual = {t.value for t in ReportType}
    assert actual == expected


def test_report_status_values():
    assert ReportStatus.QUEUED.value == "queued"
    assert ReportStatus.PROCESSING.value == "processing"
    assert ReportStatus.COMPLETED.value == "completed"
    assert ReportStatus.FAILED.value == "failed"
