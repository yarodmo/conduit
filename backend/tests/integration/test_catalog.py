"""
Conduit Tests — Material Catalog (M12) integration tests.

Coverage:
  - List items (empty + with data, category filter)
  - Create custom item (201)
  - Get item detail (200 + 404)
  - Update item price / supplier
  - Delete custom item (204) + global item guard (403)
  - Semantic search fallback (LIKE in SQLite)
  - Category list completeness
  - CSV export
  - CSV import — valid rows (created + updated)
  - CSV import — missing required columns (failed job)
  - Import job status polling
  - Supplier CRUD
  - Unauthorized → 401

Bliss Systems LLC — APEX Standard
"""

import io
import csv
import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import MEP_CATEGORIES
from app.models.takeoff import MaterialCatalog


# ══════════════════════════════════════
# HELPERS
# ══════════════════════════════════════

def _make_item_payload(**kwargs) -> dict:
    return {
        "item_type": "AHU",
        "tag_prefix": "AHU",
        "category": "HVAC",
        "specification": "Air Handling Unit 5-Ton",
        "description": "Rooftop AHU with EC motor",
        "unit": "EA",
        "base_cost_usd": "4500.00",
        "supplier_name": "Ferguson HVAC",
        **kwargs,
    }


def _make_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[
        "component_type", "tag_prefix", "category",
        "description", "unit", "unit_cost_usd",
        "supplier_name", "supplier_sku",
    ])
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


@pytest.fixture
async def catalog_item_id(client: AsyncClient, auth_headers: dict) -> str:
    resp = await client.post(
        "/api/v1/catalog/items",
        json=_make_item_payload(),
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()["id"]


@pytest.fixture
async def supplier_id(client: AsyncClient, auth_headers: dict) -> str:
    resp = await client.post(
        "/api/v1/catalog/suppliers",
        json={"name": "Test Supplier Inc", "contact_email": "test@supplier.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ══════════════════════════════════════
# LIST ITEMS
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_list_items_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/catalog/items", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_items_returns_created(
    client: AsyncClient, auth_headers: dict, catalog_item_id: str
):
    resp = await client.get("/api/v1/catalog/items", headers=auth_headers)
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()]
    assert catalog_item_id in ids


@pytest.mark.asyncio
async def test_list_items_category_filter(
    client: AsyncClient, auth_headers: dict, catalog_item_id: str
):
    resp = await client.get(
        "/api/v1/catalog/items", params={"category": "HVAC"}, headers=auth_headers
    )
    assert resp.status_code == 200
    for item in resp.json():
        assert item["category"] == "HVAC"


@pytest.mark.asyncio
async def test_list_items_wrong_category_returns_empty(
    client: AsyncClient, auth_headers: dict, catalog_item_id: str
):
    resp = await client.get(
        "/api/v1/catalog/items", params={"category": "NONEXISTENT"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ══════════════════════════════════════
# GET ITEM
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_get_item(client: AsyncClient, auth_headers: dict, catalog_item_id: str):
    resp = await client.get(f"/api/v1/catalog/items/{catalog_item_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == catalog_item_id
    assert data["is_custom"] is True
    assert data["tag_prefix"] == "AHU"
    assert data["category"] == "HVAC"


@pytest.mark.asyncio
async def test_get_item_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        f"/api/v1/catalog/items/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


# ══════════════════════════════════════
# CREATE ITEM
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_create_custom_item(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/catalog/items",
        json=_make_item_payload(specification="VAV Box 200 CFM"),
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["is_custom"] is True
    assert data["specification"] == "VAV Box 200 CFM"
    assert data["base_cost_usd"] == "4500.00"


@pytest.mark.asyncio
async def test_create_item_unauthorized(client: AsyncClient):
    resp = await client.post("/api/v1/catalog/items", json=_make_item_payload())
    assert resp.status_code == 401


# ══════════════════════════════════════
# UPDATE ITEM
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_update_item_price(
    client: AsyncClient, auth_headers: dict, catalog_item_id: str
):
    resp = await client.patch(
        f"/api/v1/catalog/items/{catalog_item_id}",
        json={"base_cost_usd": "5200.00", "supplier_name": "Wesco Supply"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["base_cost_usd"] == "5200.00"
    assert data["supplier_name"] == "Wesco Supply"


@pytest.mark.asyncio
async def test_update_global_item_forbidden(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession, test_user: dict
):
    # Global item: org_id=None, is_custom=False
    global_item = MaterialCatalog(
        org_id=None,
        item_type="PIPE",
        specification="2-inch copper pipe",
        unit="LF",
        is_custom=False,
    )
    db.add(global_item)
    await db.commit()
    await db.refresh(global_item)

    resp = await client.patch(
        f"/api/v1/catalog/items/{global_item.id}",
        json={"base_cost_usd": "10.00"},
        headers=auth_headers,
    )
    assert resp.status_code == 403


# ══════════════════════════════════════
# DELETE ITEM
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_delete_custom_item(
    client: AsyncClient, auth_headers: dict, catalog_item_id: str
):
    resp = await client.delete(
        f"/api/v1/catalog/items/{catalog_item_id}", headers=auth_headers
    )
    assert resp.status_code == 204

    # No longer visible
    get_resp = await client.get(
        f"/api/v1/catalog/items/{catalog_item_id}", headers=auth_headers
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_global_item_forbidden(
    client: AsyncClient, auth_headers: dict,
    db: AsyncSession
):
    global_item = MaterialCatalog(
        org_id=None, item_type="DUCT", specification="12x8 duct",
        unit="LF", is_custom=False,
    )
    db.add(global_item)
    await db.commit()
    await db.refresh(global_item)

    resp = await client.delete(
        f"/api/v1/catalog/items/{global_item.id}", headers=auth_headers
    )
    assert resp.status_code == 403


# ══════════════════════════════════════
# SEMANTIC SEARCH (LIKE fallback in SQLite)
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_search_returns_matching_items(
    client: AsyncClient, auth_headers: dict, catalog_item_id: str
):
    resp = await client.get(
        "/api/v1/catalog/search", params={"q": "Air Handling"}, headers=auth_headers
    )
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1
    assert all("item" in r and "score" in r for r in results)
    ids = [r["item"]["id"] for r in results]
    assert catalog_item_id in ids


@pytest.mark.asyncio
async def test_search_no_results(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/catalog/search",
        params={"q": "xyznotexistent999"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_search_query_too_short(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/catalog/search", params={"q": "x"}, headers=auth_headers
    )
    assert resp.status_code == 422


# ══════════════════════════════════════
# CATEGORIES
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_get_categories(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/catalog/categories", headers=auth_headers)
    assert resp.status_code == 200
    cats = resp.json()
    assert "HVAC" in cats
    assert "Plumbing" in cats
    assert "Electrical" in cats
    assert len(cats) == len(MEP_CATEGORIES)


# ══════════════════════════════════════
# CSV EXPORT
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_export_csv(client: AsyncClient, auth_headers: dict, catalog_item_id: str):
    resp = await client.get("/api/v1/catalog/export/csv", headers=auth_headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    content = resp.content.decode("utf-8")
    assert "component_type" in content  # header row


# ══════════════════════════════════════
# CSV IMPORT
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_import_csv_valid(client: AsyncClient, auth_headers: dict):
    csv_data = _make_csv([
        {"component_type": "FCU", "tag_prefix": "FCU", "category": "HVAC",
         "description": "Fan Coil Unit 2-pipe", "unit": "EA",
         "unit_cost_usd": "1200", "supplier_name": "Carrier", "supplier_sku": "FCU-2P"},
        {"component_type": "PUMP", "tag_prefix": "CWP", "category": "Plumbing",
         "description": "Chilled Water Pump 5HP", "unit": "EA",
         "unit_cost_usd": "3400", "supplier_name": "", "supplier_sku": ""},
    ])
    resp = await client.post(
        "/api/v1/catalog/import/csv",
        files={"file": ("test.csv", csv_data, "text/csv")},
        headers=auth_headers,
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] in ("completed", "queued", "processing")
    assert data["filename"] == "test.csv"
    assert data["rows_total"] == 2


@pytest.mark.asyncio
async def test_import_csv_missing_columns(client: AsyncClient, auth_headers: dict):
    bad_csv = b"wrong_col1,wrong_col2\nval1,val2\n"
    resp = await client.post(
        "/api/v1/catalog/import/csv",
        files={"file": ("bad.csv", bad_csv, "text/csv")},
        headers=auth_headers,
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "failed"
    assert data["errors"] is not None
    assert len(data["errors"]) > 0


@pytest.mark.asyncio
async def test_import_csv_upserts_existing(client: AsyncClient, auth_headers: dict):
    csv_row = {"component_type": "VFD", "tag_prefix": "VFD", "category": "Electrical",
               "description": "Variable Frequency Drive 5HP", "unit": "EA",
               "unit_cost_usd": "850", "supplier_name": "Eaton", "supplier_sku": ""}
    csv_data = _make_csv([csv_row])

    # First import — creates
    resp1 = await client.post(
        "/api/v1/catalog/import/csv",
        files={"file": ("vfd.csv", csv_data, "text/csv")},
        headers=auth_headers,
    )
    job1 = resp1.json()
    assert job1["rows_created"] >= 1 or job1["status"] == "queued"

    # Second import same row — updates
    csv_row["unit_cost_usd"] = "950"
    csv_data2 = _make_csv([csv_row])
    resp2 = await client.post(
        "/api/v1/catalog/import/csv",
        files={"file": ("vfd2.csv", csv_data2, "text/csv")},
        headers=auth_headers,
    )
    job2 = resp2.json()
    assert job2["status"] in ("completed", "queued")


@pytest.mark.asyncio
async def test_get_import_job(client: AsyncClient, auth_headers: dict):
    csv_data = _make_csv([
        {"component_type": "RTU", "tag_prefix": "RTU", "category": "HVAC",
         "description": "Rooftop Unit 10T", "unit": "EA",
         "unit_cost_usd": "8500", "supplier_name": "", "supplier_sku": ""},
    ])
    create_resp = await client.post(
        "/api/v1/catalog/import/csv",
        files={"file": ("rtu.csv", csv_data, "text/csv")},
        headers=auth_headers,
    )
    job_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/catalog/import/jobs/{job_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == job_id


@pytest.mark.asyncio
async def test_get_import_job_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        f"/api/v1/catalog/import/jobs/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


# ══════════════════════════════════════
# SUPPLIERS
# ══════════════════════════════════════

@pytest.mark.asyncio
async def test_create_supplier(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/catalog/suppliers",
        json={"name": "Ferguson Supply Co", "contact_email": "hvac@ferguson.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Ferguson Supply Co"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_list_suppliers(client: AsyncClient, auth_headers: dict, supplier_id: str):
    resp = await client.get("/api/v1/catalog/suppliers", headers=auth_headers)
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()]
    assert supplier_id in ids


@pytest.mark.asyncio
async def test_update_supplier(client: AsyncClient, auth_headers: dict, supplier_id: str):
    resp = await client.patch(
        f"/api/v1/catalog/suppliers/{supplier_id}",
        json={"contact_phone": "+1-800-555-0100", "website": "https://supplier.example.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["contact_phone"] == "+1-800-555-0100"


@pytest.mark.asyncio
async def test_delete_supplier(client: AsyncClient, auth_headers: dict, supplier_id: str):
    resp = await client.delete(
        f"/api/v1/catalog/suppliers/{supplier_id}", headers=auth_headers
    )
    assert resp.status_code == 204

    # Not visible in list
    list_resp = await client.get("/api/v1/catalog/suppliers", headers=auth_headers)
    ids = [s["id"] for s in list_resp.json()]
    assert supplier_id not in ids


@pytest.mark.asyncio
async def test_delete_supplier_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.delete(
        f"/api/v1/catalog/suppliers/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_supplier_unauthorized(client: AsyncClient):
    resp = await client.get("/api/v1/catalog/suppliers")
    assert resp.status_code == 401


# ══════════════════════════════════════
# UNIT — MEP_CATEGORIES completeness
# ══════════════════════════════════════

def test_mep_categories_defined():
    assert len(MEP_CATEGORIES) >= 8
    assert "HVAC" in MEP_CATEGORIES
    assert "Electrical" in MEP_CATEGORIES
    assert "Plumbing" in MEP_CATEGORIES
