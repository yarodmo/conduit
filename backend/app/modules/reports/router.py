"""
Conduit Backend — Reports Router (M9)

  POST   /reports/takeoff/{id}/export/excel       → queue Excel job
  POST   /reports/takeoff/{id}/export/pdf         → queue PDF job
  POST   /reports/project/{id}/progress-pdf       → queue progress report job
  POST   /reports/rfi/{id}/export/pdf             → queue RFI PDF job
  POST   /reports/change-order/{id}/export/pdf    → queue CO PDF job
  GET    /reports/jobs/{job_id}                   → status + presigned download URL

Bliss Systems LLC — APEX Standard
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_org, get_current_user
from app.models.auth import Organization, User
from app.models.reports import ReportType
from app.modules.reports.schemas import ReportJobResponse
from app.modules.reports.service import ReportService

router = APIRouter(tags=["Reports & Exports"])


@router.post("/reports/takeoff/{takeoff_id}/export/excel",
             response_model=ReportJobResponse, status_code=202)
async def export_takeoff_excel(
    takeoff_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ReportJobResponse:
    return await ReportService.create_job(
        db, ReportType.TAKEOFF_EXCEL, takeoff_id, org.id, current_user
    )


@router.post("/reports/takeoff/{takeoff_id}/export/pdf",
             response_model=ReportJobResponse, status_code=202)
async def export_takeoff_pdf(
    takeoff_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ReportJobResponse:
    return await ReportService.create_job(
        db, ReportType.TAKEOFF_PDF, takeoff_id, org.id, current_user
    )


@router.post("/reports/project/{project_id}/progress-pdf",
             response_model=ReportJobResponse, status_code=202)
async def export_project_progress(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ReportJobResponse:
    return await ReportService.create_job(
        db, ReportType.PROJECT_PROGRESS, project_id, org.id, current_user
    )


@router.post("/reports/rfi/{rfi_id}/export/pdf",
             response_model=ReportJobResponse, status_code=202)
async def export_rfi_pdf(
    rfi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ReportJobResponse:
    return await ReportService.create_job(
        db, ReportType.RFI_PDF, rfi_id, org.id, current_user
    )


@router.post("/reports/change-order/{co_id}/export/pdf",
             response_model=ReportJobResponse, status_code=202)
async def export_co_pdf(
    co_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ReportJobResponse:
    return await ReportService.create_job(
        db, ReportType.CHANGE_ORDER_PDF, co_id, org.id, current_user
    )


@router.get("/reports/jobs/{job_id}", response_model=ReportJobResponse)
async def get_report_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ReportJobResponse:
    return await ReportService.get_job(db, job_id, org.id)
