"""
Conduit Backend — Material Catalog Service (M12)
CRUD + semantic search (pgvector fallback to LIKE) + CSV import + suppliers.

Semantic search strategy:
  - Production (PostgreSQL + pgvector): embedding <=> query_vector ORDER BY distance
  - Test (SQLite): keyword ILIKE fallback — same interface, no embedding needed

Bliss Systems LLC — APEX Standard
"""

import csv
import io
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.catalog import CatalogImportJob, CatalogSupplier, MEP_CATEGORIES
from app.models.takeoff import MaterialCatalog
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

logger = structlog.get_logger()


def _to_item_response(item: MaterialCatalog) -> CatalogItemResponse:
    return CatalogItemResponse.model_validate(item)


def _to_supplier_response(s: CatalogSupplier) -> SupplierResponse:
    return SupplierResponse.model_validate(s)


async def _get_item(
    db: AsyncSession, item_id: uuid.UUID, org_id: uuid.UUID
) -> MaterialCatalog:
    stmt = select(MaterialCatalog).where(
        MaterialCatalog.id == item_id,
        or_(MaterialCatalog.org_id == org_id, MaterialCatalog.org_id.is_(None)),
        MaterialCatalog.is_active.is_(True),
    )
    item = (await db.execute(stmt)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Catalog item not found")
    return item


# ── Catalog Item service ───────────────────────────────────────────────────

class CatalogService:

    @staticmethod
    async def list_items(
        db: AsyncSession,
        org_id: uuid.UUID,
        category: str | None = None,
        item_type: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[CatalogItemResponse]:
        filters = [
            or_(MaterialCatalog.org_id == org_id, MaterialCatalog.org_id.is_(None)),
            MaterialCatalog.is_active.is_(True),
        ]
        if category:
            filters.append(MaterialCatalog.category == category)
        if item_type:
            filters.append(MaterialCatalog.item_type == item_type)

        stmt = (
            select(MaterialCatalog)
            .where(and_(*filters))
            .order_by(MaterialCatalog.specification)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = (await db.execute(stmt)).scalars().all()
        return [_to_item_response(i) for i in items]

    @staticmethod
    async def get_item(
        db: AsyncSession, item_id: uuid.UUID, org_id: uuid.UUID
    ) -> CatalogItemResponse:
        return _to_item_response(await _get_item(db, item_id, org_id))

    @staticmethod
    async def create_item(
        db: AsyncSession,
        org_id: uuid.UUID,
        current_user: User,
        data: CatalogItemCreate,
    ) -> CatalogItemResponse:
        item = MaterialCatalog(
            org_id=org_id,
            is_custom=True,
            **data.model_dump(),
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)

        # Queue embedding generation async (best effort)
        _queue_embedding(str(item.id), data.specification, data.tag_prefix or "")

        return _to_item_response(item)

    @staticmethod
    async def update_item(
        db: AsyncSession,
        item_id: uuid.UUID,
        org_id: uuid.UUID,
        data: CatalogItemUpdate,
    ) -> CatalogItemResponse:
        item = await _get_item(db, item_id, org_id)
        if not item.is_custom:
            raise HTTPException(status_code=403, detail="Global catalog items are read-only")

        for field, value in data.model_dump(exclude_none=True).items():
            setattr(item, field, value)
        await db.commit()
        await db.refresh(item)
        return _to_item_response(item)

    @staticmethod
    async def delete_item(
        db: AsyncSession, item_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        item = await _get_item(db, item_id, org_id)
        if not item.is_custom:
            raise HTTPException(status_code=403, detail="Only custom items can be deleted")
        if item.org_id != org_id:
            raise HTTPException(status_code=403, detail="Item belongs to another org")
        item.is_active = False
        await db.commit()

    @staticmethod
    async def get_categories() -> list[str]:
        return MEP_CATEGORIES

    @staticmethod
    async def search(
        db: AsyncSession,
        org_id: uuid.UUID,
        query: str,
        limit: int = 20,
    ) -> list[SearchResult]:
        """
        Semantic search with pgvector (PostgreSQL) or LIKE fallback (SQLite tests).
        """
        query_embedding = _get_embedding(query)

        if query_embedding is not None:
            return await _vector_search(db, org_id, query_embedding, limit)
        else:
            return await _keyword_search(db, org_id, query, limit)

    @staticmethod
    async def export_csv(
        db: AsyncSession, org_id: uuid.UUID
    ) -> bytes:
        stmt = select(MaterialCatalog).where(
            or_(MaterialCatalog.org_id == org_id, MaterialCatalog.org_id.is_(None)),
            MaterialCatalog.is_active.is_(True),
        ).order_by(MaterialCatalog.category, MaterialCatalog.item_type)
        items = (await db.execute(stmt)).scalars().all()

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=[
            "component_type", "tag_prefix", "description", "unit",
            "unit_cost_usd", "category", "supplier_name", "supplier_sku",
        ])
        writer.writeheader()
        for item in items:
            writer.writerow({
                "component_type": item.item_type,
                "tag_prefix": item.tag_prefix or "",
                "description": item.description or item.specification,
                "unit": item.unit,
                "unit_cost_usd": str(item.base_cost_usd or ""),
                "category": item.category or "",
                "supplier_name": item.supplier_name or "",
                "supplier_sku": item.supplier_sku or "",
            })
        return buf.getvalue().encode("utf-8")


# ── CSV Import ─────────────────────────────────────────────────────────────

class ImportService:

    @staticmethod
    async def create_import_job(
        db: AsyncSession,
        org_id: uuid.UUID,
        current_user: User,
        filename: str,
        csv_bytes: bytes,
    ) -> ImportJobResponse:
        # Validate CSV structure synchronously before queuing
        errors = _validate_csv(csv_bytes)
        if errors:
            job = CatalogImportJob(
                org_id=org_id,
                created_by=current_user.id,
                filename=filename,
                status="failed",
                errors=errors,
                completed_at=datetime.now(tz=timezone.utc),
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
            return ImportJobResponse.model_validate(job)

        # Count rows
        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8")))
        rows = list(reader)

        job = CatalogImportJob(
            org_id=org_id,
            created_by=current_user.id,
            filename=filename,
            status="queued",
            rows_total=len(rows),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        # Process inline (small files) or queue for worker
        if len(rows) <= 500:
            await _process_csv_inline(db, job.id, org_id, rows)
        else:
            try:
                from app.tasks.catalog_tasks import process_csv_import
                process_csv_import.delay(str(job.id), csv_bytes.decode("utf-8"))
            except Exception:
                pass

        await db.refresh(job)
        return ImportJobResponse.model_validate(job)

    @staticmethod
    async def get_import_job(
        db: AsyncSession, job_id: uuid.UUID, org_id: uuid.UUID
    ) -> ImportJobResponse:
        stmt = select(CatalogImportJob).where(
            CatalogImportJob.id == job_id, CatalogImportJob.org_id == org_id,
        )
        job = (await db.execute(stmt)).scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Import job not found")
        return ImportJobResponse.model_validate(job)


# ── Supplier service ───────────────────────────────────────────────────────

class SupplierService:

    @staticmethod
    async def create(
        db: AsyncSession, org_id: uuid.UUID, data: SupplierCreate
    ) -> SupplierResponse:
        supplier = CatalogSupplier(org_id=org_id, **data.model_dump())
        db.add(supplier)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise HTTPException(status_code=409, detail="Supplier name already exists")
        await db.refresh(supplier)
        return _to_supplier_response(supplier)

    @staticmethod
    async def update(
        db: AsyncSession, supplier_id: uuid.UUID, org_id: uuid.UUID,
        data: SupplierUpdate,
    ) -> SupplierResponse:
        stmt = select(CatalogSupplier).where(
            CatalogSupplier.id == supplier_id, CatalogSupplier.org_id == org_id,
        )
        supplier = (await db.execute(stmt)).scalar_one_or_none()
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(supplier, field, value)
        await db.commit()
        await db.refresh(supplier)
        return _to_supplier_response(supplier)

    @staticmethod
    async def delete(
        db: AsyncSession, supplier_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        stmt = select(CatalogSupplier).where(
            CatalogSupplier.id == supplier_id, CatalogSupplier.org_id == org_id,
        )
        supplier = (await db.execute(stmt)).scalar_one_or_none()
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")
        supplier.is_active = False
        await db.commit()

    @staticmethod
    async def list_suppliers(
        db: AsyncSession, org_id: uuid.UUID
    ) -> list[SupplierResponse]:
        stmt = select(CatalogSupplier).where(
            CatalogSupplier.org_id == org_id,
            CatalogSupplier.is_active.is_(True),
        ).order_by(CatalogSupplier.name)
        suppliers = (await db.execute(stmt)).scalars().all()
        return [_to_supplier_response(s) for s in suppliers]


# ── Helpers ────────────────────────────────────────────────────────────────

REQUIRED_CSV_COLUMNS = {"component_type", "description", "unit"}


def _validate_csv(csv_bytes: bytes) -> list[dict[str, Any]]:
    errors = []
    try:
        content = csv_bytes.decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            return [{"row": 0, "error": "Empty CSV or missing header row"}]
        missing = REQUIRED_CSV_COLUMNS - set(reader.fieldnames)
        if missing:
            return [{"row": 0, "error": f"Missing required columns: {', '.join(missing)}"}]
        for i, row in enumerate(reader, start=2):
            if not row.get("component_type", "").strip():
                errors.append({"row": i, "error": "component_type is required"})
            if not row.get("unit", "").strip():
                errors.append({"row": i, "error": "unit is required"})
    except Exception as e:
        errors.append({"row": 0, "error": f"CSV parse error: {e}"})
    return errors


async def _process_csv_inline(
    db: AsyncSession,
    job_id: uuid.UUID,
    org_id: uuid.UUID,
    rows: list[dict],
) -> None:
    job = await db.get(CatalogImportJob, job_id)
    if not job:
        return

    job.status = "processing"
    await db.commit()

    created = updated = failed = 0
    errors: list[dict[str, Any]] = []

    for i, row in enumerate(rows, start=2):
        try:
            item_type = row.get("component_type", "").strip()
            description = row.get("description", "").strip()
            unit = row.get("unit", "").strip()
            tag_prefix = row.get("tag_prefix", "").strip() or None
            category = row.get("category", "").strip() or None
            supplier_name = row.get("supplier_name", "").strip() or None
            supplier_sku = row.get("supplier_sku", "").strip() or None
            cost_raw = row.get("unit_cost_usd", "").strip()
            base_cost = Decimal(cost_raw) if cost_raw else None

            # Upsert: match by org + item_type + specification
            stmt = select(MaterialCatalog).where(
                MaterialCatalog.org_id == org_id,
                MaterialCatalog.item_type == item_type,
                MaterialCatalog.specification == description,
            )
            existing = (await db.execute(stmt)).scalar_one_or_none()

            if existing:
                existing.base_cost_usd = base_cost or existing.base_cost_usd
                existing.supplier_name = supplier_name or existing.supplier_name
                existing.supplier_sku = supplier_sku or existing.supplier_sku
                existing.tag_prefix = tag_prefix or existing.tag_prefix
                existing.category = category or existing.category
                updated += 1
            else:
                item = MaterialCatalog(
                    org_id=org_id,
                    item_type=item_type,
                    specification=description,
                    description=description,
                    tag_prefix=tag_prefix,
                    category=category,
                    unit=unit,
                    base_cost_usd=base_cost,
                    supplier_name=supplier_name,
                    supplier_sku=supplier_sku,
                    is_custom=True,
                )
                db.add(item)
                created += 1
        except Exception as e:
            failed += 1
            errors.append({"row": i, "error": str(e)})

    await db.commit()

    job = await db.get(CatalogImportJob, job_id)
    if job:
        job.status = "completed"
        job.rows_created = created
        job.rows_updated = updated
        job.rows_failed = failed
        job.errors = errors if errors else None
        job.completed_at = datetime.now(tz=timezone.utc)
        await db.commit()


def _get_embedding(text_input: str) -> list[float] | None:
    """Get embedding via litellm. Returns None in dev/test or on failure."""
    try:
        from app.core.config import settings
        if settings.ENVIRONMENT in ("test", "development"):
            return None
        import litellm
        resp = litellm.embedding(model="text-embedding-3-small", input=[text_input])
        return resp.data[0]["embedding"]
    except Exception:
        return None


def _queue_embedding(item_id: str, specification: str, tag_prefix: str) -> None:
    try:
        from app.tasks.catalog_tasks import generate_item_embedding
        generate_item_embedding.delay(item_id, specification, tag_prefix)
    except Exception:
        pass


async def _vector_search(
    db: AsyncSession,
    org_id: uuid.UUID,
    query_embedding: list[float],
    limit: int,
) -> list[SearchResult]:
    """PostgreSQL pgvector cosine similarity search."""
    vector_str = "[" + ",".join(str(f) for f in query_embedding) + "]"
    raw_sql = text("""
        SELECT id, (embedding::vector <=> :qvec::vector) as distance
        FROM material_catalog
        WHERE (org_id = :org_id OR org_id IS NULL)
          AND is_active = true
          AND embedding IS NOT NULL
        ORDER BY distance ASC
        LIMIT :lim
    """)
    try:
        result = await db.execute(raw_sql, {
            "qvec": vector_str, "org_id": str(org_id), "lim": limit
        })
        rows = result.fetchall()
    except Exception:
        return await _keyword_search(db, org_id, "", limit)

    items_with_scores: list[SearchResult] = []
    for row in rows:
        item = await db.get(MaterialCatalog, row[0])
        if item:
            score = max(0.0, 1.0 - float(row[1]))
            items_with_scores.append(SearchResult(
                item=_to_item_response(item), score=round(score, 4)
            ))
    return items_with_scores


async def _keyword_search(
    db: AsyncSession,
    org_id: uuid.UUID,
    query: str,
    limit: int,
) -> list[SearchResult]:
    """LIKE fallback for SQLite tests or when embedding unavailable."""
    if not query:
        return []
    pattern = f"%{query}%"
    stmt = (
        select(MaterialCatalog)
        .where(
            or_(MaterialCatalog.org_id == org_id, MaterialCatalog.org_id.is_(None)),
            MaterialCatalog.is_active.is_(True),
            or_(
                MaterialCatalog.specification.ilike(pattern),
                MaterialCatalog.item_type.ilike(pattern),
                MaterialCatalog.tag_prefix.ilike(pattern),
                MaterialCatalog.description.ilike(pattern),
            ),
        )
        .order_by(MaterialCatalog.specification)
        .limit(limit)
    )
    items = (await db.execute(stmt)).scalars().all()
    return [SearchResult(item=_to_item_response(i), score=1.0) for i in items]
