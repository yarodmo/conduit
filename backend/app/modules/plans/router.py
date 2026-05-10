"""
Conduit Backend — Plans Router (M3 + M4)

Endpoints:
  POST   /projects/{project_id}/plans/upload              → upload + dispatch pipeline
  GET    /projects/{project_id}/plans                     → list plans in project
  GET    /plans/{plan_id}/status                          → processing job status
  GET    /plans/{plan_id}/metadata                        → full plan metadata + pages
  GET    /plans/{plan_id}/pages/{page}/tiles/{z}/{x}/{y}  → tile server (< 200ms)
  WS     /ws/plans/{plan_id}/status                       → live status stream

Bliss Systems LLC — APEX Standard
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_org, get_current_user
from app.models.auth import Organization, User
from app.modules.plans.schemas import (
    PlanListItem,
    PlanMetadataResponse,
    PlanUploadResponse,
    ProcessingJobStatus,
)
from app.modules.plans.service import PlanService

router = APIRouter(tags=["Plans"])


@router.post(
    "/projects/{project_id}/plans/upload",
    response_model=PlanUploadResponse,
    status_code=202,
)
async def upload_plan(
    project_id: uuid.UUID,
    file: UploadFile = File(..., description="PDF, JPG, PNG, HEIC, or WEBP"),
    name: str | None = Form(None, description="Display name (defaults to filename)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PlanUploadResponse:
    """Upload a plan file and start background processing."""
    return await PlanService.upload(
        db=db,
        project_id=project_id,
        org_id=org.id,
        current_user=current_user,
        file=file,
        name=name,
    )


@router.get("/projects/{project_id}/plans", response_model=list[PlanListItem])
async def list_plans(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[PlanListItem]:
    """List all plans in a project."""
    return await PlanService.list_plans(
        db=db,
        project_id=project_id,
        org_id=org.id,
    )


@router.get("/plans/{plan_id}/status", response_model=ProcessingJobStatus)
async def get_plan_status(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ProcessingJobStatus:
    """Get the latest processing job status for a plan."""
    return await PlanService.get_status(
        db=db,
        plan_id=plan_id,
        org_id=org.id,
    )


@router.get("/plans/{plan_id}/metadata", response_model=PlanMetadataResponse)
async def get_plan_metadata(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> PlanMetadataResponse:
    """Get full plan metadata including detected properties and page list."""
    return await PlanService.get_metadata(
        db=db,
        plan_id=plan_id,
        org_id=org.id,
    )


@router.get(
    "/plans/{plan_id}/pages/{page}/tiles/{zoom}/{x}/{y}",
    response_class=Response,
    responses={200: {"content": {"image/webp": {}}}},
)
async def get_tile(
    plan_id: uuid.UUID,
    page: int,
    zoom: int,
    x: int,
    y: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    """
    Tile server endpoint. Returns a 256×256 WebP tile.
    Target: < 200ms with Redis cache active.
    """
    tile_bytes = await PlanService.get_tile(
        db=db,
        plan_id=plan_id,
        org_id=org.id,
        page=page,
        zoom=zoom,
        x=x,
        y=y,
    )
    return Response(
        content=tile_bytes,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=7200"},
    )


@router.websocket("/ws/plans/{plan_id}/status")
async def plan_status_ws(
    websocket: WebSocket,
    plan_id: uuid.UUID,
) -> None:
    """
    WebSocket stream for real-time processing status updates.
    Subscribes to Redis pub/sub channel plan:{plan_id}:status.
    Closes when status becomes 'ready' or 'failed'.
    """
    import json

    import redis.asyncio as aioredis

    from app.core.config import settings

    await websocket.accept()

    r = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(f"plan:{plan_id}:status")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            await websocket.send_json(data)
            if data.get("status") in ("ready", "failed"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(f"plan:{plan_id}:status")
        await r.aclose()
        try:
            await websocket.close()
        except Exception:
            pass
