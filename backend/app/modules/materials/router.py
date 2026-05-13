"""
Conduit Backend — Material Catalog Router (M12)

Catalog Items:
  GET    /catalog/items                       → list with filters
  GET    /catalog/items/{id}                  → item detail
  POST   /catalog/items                       → create custom item
  PATCH  /catalog/items/{id}                  → update org price/supplier
  DELETE /catalog/items/{id}                  → soft-delete (custom only)
  GET    /catalog/search?q=...                → semantic search (pgvector / LIKE)
  GET    /catalog/categories                  → MEP category tree

Import/Export:
  POST   /catalog/import/csv                  → bulk import from CSV
  GET    /catalog/import/jobs/{job_id}        → import job status
  GET    /catalog/export/csv                  → download org catalog as CSV

Suppliers:
  GET    /catalog/suppliers                   → list suppliers
  POST   /catalog/suppliers                   → add supplier
  PATCH  /catalog/suppliers/{id}              → edit supplier
  DELETE /catalog/suppliers/{id}              → soft-delete supplier

Bliss Systems LLC — APEX Standard
"""

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_org, get_current_user
from app.models.auth import Organization, User
from app.modules.materials.schemas import (
    CatalogItemCreate,
    CatalogItemResponse,
    CatalogItemUpdate,
    ImportJobResponse,
    SearchResult,
    SupplierCreate,
    SupplierResponse,
    SupplierUpdate,
)
from app.modules.materials.service import (
    CatalogService,
    ImportService,
    SupplierService,
)

router = APIRouter(prefix="/catalog", tags=["Material Catalog"])


# ── Catalog Items ──────────────────────────────────────────────────────────

@router.get("/items", response_model=list[CatalogItemResponse])
async def list_items(
    category: str | None = Query(None),
    item_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[CatalogItemResponse]:
    return await CatalogService.list_items(db, org.id, category, item_type, page, page_size)


@router.get("/items/{item_id}", response_model=CatalogItemResponse)
async def get_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> CatalogItemResponse:
    return await CatalogService.get_item(db, item_id, org.id)


@router.post("/items", response_model=CatalogItemResponse, status_code=201)
async def create_item(
    data: CatalogItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> CatalogItemResponse:
    return await CatalogService.create_item(db, org.id, current_user, data)


@router.patch("/items/{item_id}", response_model=CatalogItemResponse)
async def update_item(
    item_id: uuid.UUID,
    data: CatalogItemUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> CatalogItemResponse:
    return await CatalogService.update_item(db, item_id, org.id, data)


@router.delete("/items/{item_id}", status_code=204)
async def delete_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> None:
    await CatalogService.delete_item(db, item_id, org.id)


@router.get("/categories", response_model=list[str])
async def get_categories(
    _: User = Depends(get_current_user),
    __: Organization = Depends(get_current_org),
) -> list[str]:
    return await CatalogService.get_categories()


@router.get("/search", response_model=list[SearchResult])
async def search_catalog(
    q: str = Query(min_length=2, description="Natural language query"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[SearchResult]:
    return await CatalogService.search(db, org.id, q, limit)


# ── Import / Export ────────────────────────────────────────────────────────

@router.post("/import/csv", response_model=ImportJobResponse, status_code=202)
async def import_csv(
    file: UploadFile = File(..., description="CSV with columns: component_type, description, unit"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ImportJobResponse:
    csv_bytes = await file.read()
    return await ImportService.create_import_job(
        db, org.id, current_user, file.filename or "import.csv", csv_bytes
    )


@router.get("/import/jobs/{job_id}", response_model=ImportJobResponse)
async def get_import_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ImportJobResponse:
    return await ImportService.get_import_job(db, job_id, org.id)


@router.get("/export/csv")
async def export_csv(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    data = await CatalogService.export_csv(db, org.id)
    return Response(
        content=data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=catalog.csv"},
    )


# ── Suppliers ──────────────────────────────────────────────────────────────

@router.get("/suppliers", response_model=list[SupplierResponse])
async def list_suppliers(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> list[SupplierResponse]:
    return await SupplierService.list_suppliers(db, org.id)


@router.post("/suppliers", response_model=SupplierResponse, status_code=201)
async def create_supplier(
    data: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SupplierResponse:
    return await SupplierService.create(db, org.id, data)


@router.patch("/suppliers/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: uuid.UUID,
    data: SupplierUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> SupplierResponse:
    return await SupplierService.update(db, supplier_id, org.id, data)


@router.delete("/suppliers/{supplier_id}", status_code=204)
async def delete_supplier(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> None:
    await SupplierService.delete(db, supplier_id, org.id)
