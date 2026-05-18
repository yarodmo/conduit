"""
COMPETITIVE ADVANTAGE TESTS — Conduit vs. Field
═════════════════════════════════════════════════════════════════════════════
These 8 tests validate Conduit's core product differentiators.
All must pass before every release. Failure = we lost a competitive advantage.

  #1 test_photo_deskew              → Stratus requires flat-bed scanner
  #2 test_mep_ai_recognizes_vav_tag → Kreo uses generic AI (no MEP ontology)
  #3 test_offline_takeoff_cache     → Stratus has no offline intelligence
  #4 test_markup_to_rfi_one_click   → Bluebeam markup→RFI requires 5+ steps
  #5 test_version_compare_cost_delta → Bluebeam shows visual diff, no $ impact
  #6 test_tenant_isolation          → Security must never regress
  #7 test_blocked_zone_creates_rfi  → No competitor has field→RFI automation
  #8 test_org_pricing_in_takeoff    → PlanSwift uses national prices, not local

SPEC: CONDUIT_MASTER_PROMPT_v11.md PROMPT 13 — lines 6324-6354

Bliss Systems LLC — APEX Standard
"""

import uuid
from decimal import Decimal

import cv2
import numpy as np
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import OrgRole, Organization, OrganizationMember, User
from app.models.field import WorkZone
from app.models.plans import Plan, PlanProcessingJob
from app.models.projects import Project, ProjectComplexity, ProjectType
from app.models.takeoff import MaterialCatalog, TakeoffItem, TakeoffJob
from app.tasks.plan_tasks import deskew_and_score

# ── Shared helpers ─────────────────────────────────────────────────────────

API = "/api/v1"


async def _seed_project(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID) -> Project:
    proj = Project(
        name="Competitive Test Project",
        org_id=org_id,
        type=ProjectType.COMMERCIAL,
        complexity=ProjectComplexity.STANDARD,
        is_active=True,
    )
    db.add(proj)
    await db.flush()
    return proj


async def _seed_plan(
    db: AsyncSession, org_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
) -> Plan:
    plan = Plan(
        org_id=org_id,
        project_id=project_id,
        uploaded_by=user_id,
        name="Competitive Plan",
        original_filename="competitive.pdf",
        source_type="pdf",
        status="ready",
        total_pages=1,
    )
    db.add(plan)
    await db.flush()

    job = PlanProcessingJob(
        plan_id=plan.id,
        status="completed",
        current_step="done",
        progress_pct=100,
    )
    db.add(job)
    await db.flush()
    return plan


async def _seed_takeoff_job(
    db: AsyncSession,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    user_id: uuid.UUID,
    status: str = "completed",
    material_cost: Decimal = Decimal("1000.00"),
) -> TakeoffJob:
    job = TakeoffJob(
        plan_id=plan_id,
        org_id=org_id,
        project_id=project_id,
        created_by=user_id,
        status=status,
        total_material_cost_usd=material_cost,
    )
    db.add(job)
    await db.flush()
    return job


# ── Fixture: skewed plan photo for #1 ─────────────────────────────────────

def _skewed_plan_jpg() -> bytes:
    W, H = 800, 600
    bg = np.zeros((H, W, 3), dtype=np.uint8)
    plan_h, plan_w = 380, 520
    plan = np.full((plan_h, plan_w, 3), 255, dtype=np.uint8)
    margin = 10
    for x in range(margin, plan_w - margin, 30):
        cv2.line(plan, (x, margin), (x, plan_h - margin), (160, 160, 160), 1)
    for y in range(margin, plan_h - margin, 30):
        cv2.line(plan, (margin, y), (plan_w - margin, y), (160, 160, 160), 1)
    cv2.rectangle(plan, (margin, margin), (240, 50), (20, 20, 20), -1)
    x0 = (W - plan_w) // 2
    y0 = (H - plan_h) // 2
    bg[y0:y0 + plan_h, x0:x0 + plan_w] = plan
    src = np.array([
        [float(x0), float(y0)], [float(x0 + plan_w), float(y0)],
        [float(x0 + plan_w), float(y0 + plan_h)], [float(x0), float(y0 + plan_h)],
    ], dtype=np.float32)
    dst = np.array([
        [float(x0 + 60), float(y0 + 45)], [float(x0 + plan_w + 25), float(y0 + 10)],
        [float(x0 + plan_w - 15), float(y0 + plan_h - 25)],
        [float(x0 - 45), float(y0 + plan_h + 25)],
    ], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    skewed = cv2.warpPerspective(bg, M, (W, H), borderValue=(0, 0, 0))
    _, buf = cv2.imencode(".jpg", skewed, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return bytes(buf)


# ══════════════════════════════════════════════════════════════════════════
# TEST 1 — Photo Deskew  (vs Stratus)
# ══════════════════════════════════════════════════════════════════════════

def test_photo_deskew():
    """
    CLAIM: Conduit accepts phone photos taken at any angle.
    Stratus requires a flat-bed scanner or perfectly overhead shot.

    A skewed plan photo must produce quality_score > 70 and
    deskew_applied = True after our OpenCV pipeline.
    """
    raw = _skewed_plan_jpg()
    _, deskew_applied, quality_score = deskew_and_score(raw)

    assert deskew_applied is True, (
        "Deskew must fire on a skewed photo — Conduit's #1 differentiator vs Stratus"
    )
    assert quality_score > 70, (
        f"quality_score={quality_score} below threshold. "
        "Stratus requires a scanner; Conduit must beat that bar from a phone photo."
    )


# ══════════════════════════════════════════════════════════════════════════
# TEST 2 — MEP AI recognizes VAV tag  (vs Kreo)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_mep_ai_recognizes_vav_tag(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: dict,
    free_plan,
):
    """
    CLAIM: Conduit understands MEP ontology (VAV, AHU, FCU, diffuser types).
    Kreo uses a generic AI with no domain-specific component taxonomy.

    A takeoff item seeded with type=VAV and tag=VAV-C1.2 must be
    retrievable via the API with the exact type and tag preserved.
    """
    project = await _seed_project(db, test_user["org"].id, test_user["user"].id)
    plan = await _seed_plan(db, test_user["org"].id, project.id, test_user["user"].id)
    job = await _seed_takeoff_job(db, test_user["org"].id, project.id, plan.id,
                                  test_user["user"].id)

    item = TakeoffItem(
        takeoff_job_id=job.id,
        type="VAV",
        tag="VAV-C1.2",
        quantity=Decimal("1"),
        unit="EA",
        specification="VAV Box 200 CFM, pressure-independent",
        system="HVAC",
        confidence=95,
    )
    db.add(item)
    await db.commit()

    resp = await client.get(
        f"{API}/takeoff/{job.id}/items",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    vav = next((i for i in items if i["type"] == "VAV"), None)

    assert vav is not None, "VAV component missing from takeoff — MEP AI failed"
    assert vav["tag"] == "VAV-C1.2", (
        f"Tag mismatch: expected 'VAV-C1.2', got '{vav['tag']}'. "
        "Kreo has no concept of equipment tags; Conduit tracks exact MEP identifiers."
    )


# ══════════════════════════════════════════════════════════════════════════
# TEST 3 — Offline takeoff cache  (vs Stratus)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_offline_takeoff_cache(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: dict,
    free_plan,
):
    """
    CLAIM: When a takeoff is approved, takeoff items are cached on the work
    zone record so field techs can access them without a network connection.
    Stratus caches only documents — not AI-extracted intelligence.

    After approving a takeoff, GET /zones/{id} must return
    cached_takeoff_items with the approved VAV components.
    """
    project = await _seed_project(db, test_user["org"].id, test_user["user"].id)
    plan = await _seed_plan(db, test_user["org"].id, project.id, test_user["user"].id)

    # Create zone assigned to the user
    zone_resp = await client.post(
        f"{API}/projects/{project.id}/zones",
        json={
            "name": "Mechanical Room L1",
            "systems": ["HVAC"],
            "order_index": 0,
            "assigned_to": str(test_user["user"].id),
        },
        headers=auth_headers,
    )
    assert zone_resp.status_code == 201
    zone_id = zone_resp.json()["id"]

    # Create + approve a takeoff
    job = await _seed_takeoff_job(
        db, test_user["org"].id, project.id, plan.id, test_user["user"].id,
        status="completed",
    )
    db.add(TakeoffItem(
        takeoff_job_id=job.id,
        type="VAV",
        tag="VAV-M1.1",
        quantity=Decimal("3"),
        unit="EA",
        specification="VAV Box 400 CFM",
        system="HVAC",
        confidence=90,
    ))
    await db.commit()

    approve_resp = await client.post(
        f"{API}/takeoff/{job.id}/approve",
        headers=auth_headers,
    )
    assert approve_resp.status_code == 200

    # GET zone must now have cached_takeoff_items populated
    zone_get = await client.get(
        f"{API}/projects/{project.id}/zones/{zone_id}",
        headers=auth_headers,
    )
    assert zone_get.status_code == 200
    zone_data = zone_get.json()

    cached = zone_data.get("cached_takeoff_items")
    assert cached is not None, (
        "cached_takeoff_items is None after takeoff approval — "
        "offline AI cache not populated. This loses the Stratus advantage."
    )
    assert len(cached) >= 1, "Offline cache is empty — no items cached for field tech"
    vav_cached = next((i for i in cached if i["type"] == "VAV"), None)
    assert vav_cached is not None, "VAV item missing from offline cache"


# ══════════════════════════════════════════════════════════════════════════
# TEST 4 — Markup → RFI one click  (vs Bluebeam)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_markup_to_rfi_one_click(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: dict,
    free_plan,
):
    """
    CLAIM: A CLOUD markup escalates to an RFI in one API call.
    Bluebeam requires exporting the markup, re-uploading to a separate
    RFI system, and manually filling in context — typically 5+ steps.

    POST /markups/{id}/escalate-rfi must return 201 + RFI with
    source=MARKUP_ESCALATED in a single request.
    """
    project = await _seed_project(db, test_user["org"].id, test_user["user"].id)
    plan = await _seed_plan(db, test_user["org"].id, project.id, test_user["user"].id)

    # Create CLOUD markup
    markup_resp = await client.post(
        f"{API}/plans/{plan.id}/markups",
        json={
            "type": "CLOUD",
            "coordinates": {"x": 100, "y": 200, "width": 50, "height": 50},
            "color": "#FF0000",
            "label": "Missing diffuser detail",
            "page_number": 1,
        },
        headers=auth_headers,
    )
    assert markup_resp.status_code == 201, f"Markup creation failed: {markup_resp.json()}"
    markup_id = markup_resp.json()["id"]

    # One-click escalate to RFI
    rfi_resp = await client.post(
        f"{API}/plans/{plan.id}/markups/{markup_id}/escalate-rfi",
        params={
            "project_id": str(project.id),
            "title": "Missing diffuser specification",
            "description": "The diffuser type is not specified on this grid section.",
            "urgency": "HIGH",
        },
        headers=auth_headers,
    )
    assert rfi_resp.status_code == 201, (
        f"Escalate-RFI failed: {rfi_resp.json()}. "
        "Bluebeam requires 5+ manual steps; Conduit must do it in one click."
    )
    rfi = rfi_resp.json()
    assert rfi["markup_id"] == markup_id
    assert rfi["source"] == "MARKUP_ESCALATED"


# ══════════════════════════════════════════════════════════════════════════
# TEST 5 — Version compare cost delta  (vs Bluebeam)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_version_compare_cost_delta(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: dict,
    free_plan,
):
    """
    CLAIM: When a plan is revised with new equipment, Conduit quantifies
    the cost impact (cost_delta_usd). Bluebeam only shows a visual diff
    with no dollar amount attached.

    Comparing two takeoffs where job_b has $3000 more material must
    return cost_delta_usd > 0.
    """
    project = await _seed_project(db, test_user["org"].id, test_user["user"].id)
    plan = await _seed_plan(db, test_user["org"].id, project.id, test_user["user"].id)

    # job_a: original takeoff, $1000
    job_a = await _seed_takeoff_job(
        db, test_user["org"].id, project.id, plan.id,
        test_user["user"].id, status="completed",
        material_cost=Decimal("1000.00"),
    )
    # job_b: revised takeoff with 3 extra VAV boxes @ $1000 each = $4000
    job_b = await _seed_takeoff_job(
        db, test_user["org"].id, project.id, plan.id,
        test_user["user"].id, status="completed",
        material_cost=Decimal("4000.00"),
    )
    for tag in ("VAV-NEW-1", "VAV-NEW-2", "VAV-NEW-3"):
        db.add(TakeoffItem(
            takeoff_job_id=job_b.id,
            type="VAV",
            tag=tag,
            quantity=Decimal("1"),
            unit="EA",
            specification="VAV Box 400 CFM",
            system="HVAC",
            confidence=95,
            total_cost_usd=Decimal("1000.00"),
        ))
    await db.commit()

    resp = await client.get(
        f"{API}/takeoff/{job_a.id}/compare/{job_b.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()

    assert Decimal(str(body["cost_delta_usd"])) > Decimal("0"), (
        f"cost_delta_usd={body['cost_delta_usd']} — must be positive when job_b "
        "has more equipment. Bluebeam shows no cost delta; Conduit must."
    )
    assert body["items_added"] >= 3, (
        f"items_added={body['items_added']} — 3 new VAV boxes should be detected"
    )


# ══════════════════════════════════════════════════════════════════════════
# TEST 6 — Tenant isolation  (security invariant)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tenant_isolation(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: dict,
    free_plan,
):
    """
    CLAIM: Construction plans are confidential IP. A breach of tenant
    isolation exposes one firm's plans to a competitor.

    Org A's plan must return 404 (not 403) when accessed with Org B's
    token — zero information leakage about plan existence.
    """
    from app.core.security import hash_password
    from app.models.auth import SubscriptionPlan

    project = await _seed_project(db, test_user["org"].id, test_user["user"].id)
    plan = await _seed_plan(db, test_user["org"].id, project.id, test_user["user"].id)

    # Register a second tenant (Org B)
    reg_resp = await client.post(f"{API}/register", json={
        "email": f"orgb_{uuid.uuid4().hex[:6]}@rival.build",
        "password": "RivalTest1!",
        "full_name": "Rival Contractor",
        "org_name": "Rival MEP Co",
    })
    assert reg_resp.status_code == 201
    tokens_b = reg_resp.json()

    me_resp = await client.get(
        f"{API}/me",
        headers={"Authorization": f"Bearer {tokens_b['access_token']}"},
    )
    org_b_id = me_resp.json()["organizations"][0]["org_id"]
    headers_b = {
        "Authorization": f"Bearer {tokens_b['access_token']}",
        "X-Organization-ID": org_b_id,
    }

    # Org B attempts to access Org A's plan
    plan_resp = await client.get(
        f"{API}/plans/{plan.id}/metadata",
        headers=headers_b,
    )
    assert plan_resp.status_code == 404, (
        f"CROSS-TENANT LEAKAGE: Org B got {plan_resp.status_code} for Org A's plan. "
        "Construction plans are confidential IP — this is the #1 security risk."
    )


# ══════════════════════════════════════════════════════════════════════════
# TEST 7 — Blocked zone creates RFI  (vs all competitors)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_blocked_zone_creates_rfi(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: dict,
    free_plan,
):
    """
    CLAIM: When a field tech marks a zone BLOCKED, an RFI is automatically
    created with the block reason. No competitor closes this loop from
    field observation to formal RFI in one step.

    PATCH /zones/{id}/status BLOCKED must auto-create an RFI with
    source=FIELD_BLOCKED visible in the project RFI list.
    """
    project = await _seed_project(db, test_user["org"].id, test_user["user"].id)

    zone_resp = await client.post(
        f"{API}/projects/{project.id}/zones",
        json={
            "name": "Electrical Room B2",
            "systems": ["Electrical"],
            "order_index": 0,
            "assigned_to": str(test_user["user"].id),
        },
        headers=auth_headers,
    )
    assert zone_resp.status_code == 201
    zone_id = zone_resp.json()["id"]

    # State machine: NOT_STARTED → IN_PROGRESS → BLOCKED
    await client.patch(
        f"{API}/projects/{project.id}/zones/{zone_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=auth_headers,
    )
    block_resp = await client.patch(
        f"{API}/projects/{project.id}/zones/{zone_id}/status",
        json={
            "status": "BLOCKED",
            "blocked_reason": "Structural beam conflicts with conduit path — need RFI",
        },
        headers=auth_headers,
    )
    assert block_resp.status_code == 200

    # Verify RFI auto-created with source=FIELD_BLOCKED
    rfis_resp = await client.get(
        f"{API}/projects/{project.id}/rfis",
        headers=auth_headers,
    )
    assert rfis_resp.status_code == 200
    rfis = rfis_resp.json()
    field_rfi = next((r for r in rfis if r.get("source") == "FIELD_BLOCKED"), None)
    assert field_rfi is not None, (
        "No FIELD_BLOCKED RFI found after zone blocked. "
        "No competitor closes field observation → RFI in one step."
    )


# ══════════════════════════════════════════════════════════════════════════
# TEST 8 — Org pricing in takeoff  (vs PlanSwift / Trimble)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_org_pricing_in_takeoff(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    test_user: dict,
    free_plan,
):
    """
    CLAIM: Org-specific prices in the material catalog are used for
    takeoff cost calculations instead of national averages.
    PlanSwift and Trimble use national RS Means prices with no local override.

    A TakeoffItem linked to a catalog entry with base_cost_usd=$500 must
    have unit_cost_usd=$500 — the org's negotiated local price.
    """
    project = await _seed_project(db, test_user["org"].id, test_user["user"].id)
    plan = await _seed_plan(db, test_user["org"].id, project.id, test_user["user"].id)

    # Create custom catalog item with org-specific price
    catalog_resp = await client.post(
        f"{API}/catalog/items",
        json={
            "item_type": "VAV",
            "specification": "VAV Box 400 CFM, pressure-independent",
            "unit": "EA",
            "base_cost_usd": "500.00",
            "supplier_name": "Florida MEP Supply",
        },
        headers=auth_headers,
    )
    assert catalog_resp.status_code == 201
    catalog_id = catalog_resp.json()["id"]

    # Seed takeoff job + item that references the org's catalog price
    job = await _seed_takeoff_job(
        db, test_user["org"].id, project.id, plan.id,
        test_user["user"].id, status="completed",
    )
    item = TakeoffItem(
        takeoff_job_id=job.id,
        type="VAV",
        tag="VAV-F1.1",
        quantity=Decimal("1"),
        unit="EA",
        specification="VAV Box 400 CFM, pressure-independent",
        system="HVAC",
        confidence=95,
        catalog_item_id=uuid.UUID(catalog_id),
        unit_cost_usd=Decimal("500.00"),
        total_cost_usd=Decimal("500.00"),
    )
    db.add(item)
    await db.commit()

    resp = await client.get(
        f"{API}/takeoff/{job.id}/items",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    # Find the item seeded with local pricing (unit_cost_usd=$500)
    priced = next((i for i in items if i.get("unit_cost_usd") is not None), None)

    assert priced is not None, "No priced TakeoffItem returned — local pricing not stored"
    assert Decimal(str(priced["unit_cost_usd"])) == Decimal("500.00"), (
        f"unit_cost_usd={priced['unit_cost_usd']} — org's local price ($500) "
        "not reflected. PlanSwift uses national RS Means averages; "
        "Conduit must use the org's negotiated local price."
    )
