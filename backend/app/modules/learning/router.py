"""
Conduit Backend — Self-Learning Pipeline Router (M13)

  GET    /learning/dashboard        → full learning dashboard (latest insight + KPIs)
  GET    /learning/insights/latest  → most recent analysis report
  POST   /learning/trigger          → manually trigger analysis (admin)

Bliss Systems LLC — APEX Standard
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_org, get_current_user
from app.models.auth import Organization, User
from app.modules.learning.schemas import (
    InsightResponse,
    LearningDashboardResponse,
    TriggerAnalysisResponse,
)
from app.modules.learning.service import LearningService

router = APIRouter(prefix="/learning", tags=["Self-Learning Pipeline"])


@router.get("/dashboard", response_model=LearningDashboardResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> LearningDashboardResponse:
    """Learning dashboard: accuracy trends, top error patterns, correction stats."""
    return await LearningService.get_dashboard(db, org.id)


@router.get("/insights/latest", response_model=InsightResponse)
async def get_latest_insight(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> InsightResponse:
    """Most recent weekly analysis report."""
    return await LearningService.get_latest_insight(db, org.id)


@router.post("/trigger", response_model=TriggerAnalysisResponse)
async def trigger_analysis(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> TriggerAnalysisResponse:
    """Manually trigger learning analysis for org. Used by admins or for testing."""
    return await LearningService.run_analysis(db, org.id)
