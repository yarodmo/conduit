"""Conduit Backend — Material Catalog Schemas (M12). Bliss Systems LLC — APEX Standard"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


# ── Catalog Item ──────────────────────────────────────────────────────────

class CatalogItemCreate(BaseModel):
    item_type: str = Field(min_length=1, max_length=50)
    tag_prefix: str | None = Field(None, max_length=50)
    category: str | None = None
    specification: str = Field(min_length=1, max_length=512)
    description: str | None = None
    unit: str = Field(min_length=1, max_length=10)
    base_cost_usd: Decimal | None = None
    supplier_name: str | None = None
    supplier_sku: str | None = None
    supplier_contact: str | None = None
    supplier_lead_days: int | None = None


class CatalogItemUpdate(BaseModel):
    base_cost_usd: Decimal | None = None
    supplier_name: str | None = None
    supplier_sku: str | None = None
    supplier_contact: str | None = None
    supplier_lead_days: int | None = None
    is_active: bool | None = None
    description: str | None = None


class CatalogItemResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID | None
    item_type: str
    tag_prefix: str | None
    category: str | None
    specification: str
    description: str | None
    unit: str
    base_cost_usd: Decimal | None
    supplier_name: str | None
    supplier_sku: str | None
    supplier_contact: str | None
    supplier_lead_days: int | None
    is_custom: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Supplier ──────────────────────────────────────────────────────────────

class SupplierCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    contact_email: str | None = None
    contact_phone: str | None = None
    website: str | None = None
    notes: str | None = None


class SupplierUpdate(BaseModel):
    contact_email: str | None = None
    contact_phone: str | None = None
    website: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class SupplierResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    contact_email: str | None
    contact_phone: str | None
    website: str | None
    notes: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Import ────────────────────────────────────────────────────────────────

class ImportJobResponse(BaseModel):
    id: uuid.UUID
    status: str
    filename: str
    rows_total: int | None
    rows_created: int
    rows_updated: int
    rows_failed: int
    errors: list[dict[str, Any]] | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# ── Search ────────────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    item: CatalogItemResponse
    score: float  # similarity score 0–1 (1 = exact)
