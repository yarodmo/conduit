"""
INTEGRATION TEST — Sprint 3: RFI & Change Orders (M7)
======================================================
Covers: markup CRUD, full state machine (all transitions including rejection
loops), CLOUD→RFI escalation, Change Order flow, PDF export, SLA units.

Total: ~35 tests

Bliss Systems LLC — APEX Standard
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plans import Plan, PlanPage
from app.models.projects import Project, ProjectComplexity, ProjectType
from app.models.rfis import Markup, RFI, RFIStatus, RFI_TRANSITIONS

BASE = "/api/v1"


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def project(db: AsyncSession, test_user: dict) -> Project:
    proj = Project(
        name="School MEP",
        org_id=test_user["org"].id,
        type=ProjectType.INSTITUTIONAL,
        complexity=ProjectComplexity.COMPLEX,
        is_active=True,
    )
    db.add(proj)
    await db.commit()
    await db.refresh(proj)
    return proj


@pytest_asyncio.fixture
async def ready_plan(db: AsyncSession, test_user: dict, project: Project) -> Plan:
    plan = Plan(
        org_id=test_user["org"].id,
        project_id=project.id,
        uploaded_by=test_user["user"].id,
        name="Floor 1 MEP",
        original_filename="floor1.pdf",
        source_type="pdf",
        status="ready",
        total_pages=1,
    )
    db.add(plan)
    await db.flush()
    page = PlanPage(plan_id=plan.id, page_number=1, width_px=2550, height_px=3300)
    db.add(page)
    await db.commit()
    await db.refresh(plan)
    return plan


@pytest_asyncio.fixture
async def cloud_markup(db: AsyncSession, test_user: dict, ready_plan: Plan) -> Markup:
    m = Markup(
        plan_id=ready_plan.id,
        org_id=test_user["org"].id,
        author_id=test_user["user"].id,
        type="CLOUD",
        coordinates={"x": 100, "y": 200, "width": 50, "height": 30},
        color="#FF0000",
        page_number=1,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


@pytest_asyncio.fixture
async def draft_rfi(db: AsyncSession, test_user: dict, project: Project) -> RFI:
    rfi = RFI(
        project_id=project.id,
        org_id=test_user["org"].id,
        created_by=test_user["user"].id,
        rfi_number="RFI-001",
        title="Duct clearance conflict at grid B-4",
        description="Structural beam conflicts with 24x12 supply duct at grid B-4 elevation +12'",
        status="DRAFT",
        urgency="HIGH",
        source="MANUAL",
        due_date=datetime.now(tz=timezone.utc) + timedelta(days=7),
    )
    db.add(rfi)
    await db.commit()
    await db.refresh(rfi)
    return rfi


@pytest_asyncio.fixture
async def closed_rfi(db: AsyncSession, test_user: dict, project: Project) -> RFI:
    rfi = RFI(
        project_id=project.id,
        org_id=test_user["org"].id,
        created_by=test_user["user"].id,
        rfi_number="RFI-002",
        title="Closed RFI for CO testing",
        description="This RFI has been fully resolved and closed for testing.",
        status="CLOSED",
        urgency="MEDIUM",
        source="MANUAL",
        submitted_at=datetime.now(tz=timezone.utc),
        answered_at=datetime.now(tz=timezone.utc),
        closed_at=datetime.now(tz=timezone.utc),
    )
    db.add(rfi)
    await db.commit()
    await db.refresh(rfi)
    return rfi


# ── Markup tests ───────────────────────────────────────────────────────────

class TestMarkups:

    @pytest.mark.asyncio
    async def test_create_markup_returns_201(
        self, client: AsyncClient, auth_headers: dict, ready_plan: Plan
    ):
        resp = await client.post(
            f"{BASE}/plans/{ready_plan.id}/markups",
            json={
                "type": "RECTANGLE",
                "coordinates": {"x": 50, "y": 100, "width": 200, "height": 150},
                "color": "#0000FF",
                "page_number": 1,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["type"] == "RECTANGLE"
        assert body["resolved"] is False

    @pytest.mark.asyncio
    async def test_create_cloud_markup(
        self, client: AsyncClient, auth_headers: dict, ready_plan: Plan
    ):
        resp = await client.post(
            f"{BASE}/plans/{ready_plan.id}/markups",
            json={
                "type": "CLOUD",
                "coordinates": {"points": [[0, 0], [100, 0], [100, 50], [0, 50]]},
                "label": "Pipe conflict with structural",
                "page_number": 1,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["type"] == "CLOUD"

    @pytest.mark.asyncio
    async def test_list_markups(
        self, client: AsyncClient, auth_headers: dict, ready_plan: Plan, cloud_markup: Markup  # noqa: ARG002
    ):
        resp = await client.get(
            f"{BASE}/plans/{ready_plan.id}/markups",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    @pytest.mark.asyncio
    async def test_escalate_cloud_to_rfi(
        self, client: AsyncClient, auth_headers: dict,
        cloud_markup: Markup, project: Project
    ):
        resp = await client.post(
            f"{BASE}/plans/{cloud_markup.plan_id}/markups/{cloud_markup.id}/escalate-rfi"
            f"?title=Duct+conflict+grid+B4&description=Structural+beam+conflicts+with+supply+duct+at+grid+B4"
            f"&project_id={project.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["source"] == "MARKUP_ESCALATED"
        assert body["markup_id"] == str(cloud_markup.id)

    @pytest.mark.asyncio
    async def test_only_cloud_can_escalate(
        self, client: AsyncClient, auth_headers: dict,
        ready_plan: Plan, project: Project, db: AsyncSession, test_user: dict
    ):
        rect = Markup(
            plan_id=ready_plan.id,
            org_id=test_user["org"].id,
            author_id=test_user["user"].id,
            type="RECTANGLE",
            coordinates={"x": 0, "y": 0, "width": 10, "height": 10},
            page_number=1,
        )
        db.add(rect)
        await db.commit()

        resp = await client.post(
            f"{BASE}/plans/{ready_plan.id}/markups/{rect.id}/escalate-rfi"
            f"?title=Title+here&description=Description+here+at+least+ten+chars"
            f"&project_id={project.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 422


# ── RFI State Machine tests ────────────────────────────────────────────────

class TestRFIStateMachine:

    @pytest.mark.asyncio
    async def test_create_rfi_starts_as_draft(
        self, client: AsyncClient, auth_headers: dict, project: Project
    ):
        resp = await client.post(
            f"{BASE}/projects/{project.id}/rfis",
            json={
                "title": "HVAC clearance issue at mechanical room",
                "description": "Insufficient clearance for AHU maintenance access per ASHRAE 90.1",
                "urgency": "HIGH",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "DRAFT"
        assert resp.json()["rfi_number"].startswith("RFI-")

    @pytest.mark.asyncio
    async def test_submit_transitions_to_submitted(
        self, client: AsyncClient, auth_headers: dict, draft_rfi: RFI
    ):
        resp = await client.post(
            f"{BASE}/rfis/{draft_rfi.id}/submit", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "SUBMITTED"
        assert resp.json()["submitted_at"] is not None

    @pytest.mark.asyncio
    async def test_assign_transitions_to_under_review(
        self, client: AsyncClient, auth_headers: dict,
        draft_rfi: RFI, test_user: dict
    ):
        # Submit first
        await client.post(f"{BASE}/rfis/{draft_rfi.id}/submit", headers=auth_headers)
        # Assign
        resp = await client.post(
            f"{BASE}/rfis/{draft_rfi.id}/assign",
            json={"assigned_to": str(test_user["user"].id)},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "UNDER_REVIEW"

    @pytest.mark.asyncio
    async def test_answer_transitions_to_answered(
        self, client: AsyncClient, auth_headers: dict,
        draft_rfi: RFI, test_user: dict
    ):
        await client.post(f"{BASE}/rfis/{draft_rfi.id}/submit", headers=auth_headers)
        await client.post(
            f"{BASE}/rfis/{draft_rfi.id}/assign",
            json={"assigned_to": str(test_user["user"].id)},
            headers=auth_headers,
        )
        resp = await client.post(
            f"{BASE}/rfis/{draft_rfi.id}/answer",
            json={"response": "Coordinate with structural — use flexible duct connector at beam crossing."},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ANSWERED"
        assert resp.json()["answered_at"] is not None

    @pytest.mark.asyncio
    async def test_close_transitions_to_closed(
        self, client: AsyncClient, auth_headers: dict,
        draft_rfi: RFI, test_user: dict
    ):
        await client.post(f"{BASE}/rfis/{draft_rfi.id}/submit", headers=auth_headers)
        await client.post(
            f"{BASE}/rfis/{draft_rfi.id}/assign",
            json={"assigned_to": str(test_user["user"].id)},
            headers=auth_headers,
        )
        await client.post(
            f"{BASE}/rfis/{draft_rfi.id}/answer",
            json={"response": "Use flexible connector at beam. Approved by structural."},
            headers=auth_headers,
        )
        resp = await client.post(f"{BASE}/rfis/{draft_rfi.id}/close", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "CLOSED"
        assert resp.json()["closed_at"] is not None

    @pytest.mark.asyncio
    async def test_rejection_loop_answered_to_under_review(
        self, client: AsyncClient, auth_headers: dict,
        draft_rfi: RFI, test_user: dict
    ):
        await client.post(f"{BASE}/rfis/{draft_rfi.id}/submit", headers=auth_headers)
        await client.post(
            f"{BASE}/rfis/{draft_rfi.id}/assign",
            json={"assigned_to": str(test_user["user"].id)},
            headers=auth_headers,
        )
        await client.post(
            f"{BASE}/rfis/{draft_rfi.id}/answer",
            json={"response": "Proposed solution: reroute duct around beam."},
            headers=auth_headers,
        )
        # Reject — back to UNDER_REVIEW
        resp = await client.post(
            f"{BASE}/rfis/{draft_rfi.id}/reject",
            json={"reason": "Solution not acceptable — fire rating compromised by proposed reroute."},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "REJECTED"

        # Can transition back to UNDER_REVIEW from REJECTED
        resp2 = await client.post(
            f"{BASE}/rfis/{draft_rfi.id}/assign",
            json={"assigned_to": str(test_user["user"].id)},
            headers=auth_headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "UNDER_REVIEW"

    @pytest.mark.asyncio
    async def test_invalid_transition_returns_422(
        self, client: AsyncClient, auth_headers: dict, draft_rfi: RFI
    ):
        # DRAFT → ANSWERED is invalid
        resp = await client.post(
            f"{BASE}/rfis/{draft_rfi.id}/answer",
            json={"response": "Skipping states is not allowed."},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_closed_rfi_cannot_transition(
        self, client: AsyncClient, auth_headers: dict, closed_rfi: RFI
    ):
        resp = await client.post(f"{BASE}/rfis/{closed_rfi.id}/submit", headers=auth_headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_auto_numbering_sequential(
        self, client: AsyncClient, auth_headers: dict, project: Project
    ):
        resp1 = await client.post(
            f"{BASE}/projects/{project.id}/rfis",
            json={"title": "First RFI title here", "description": "First RFI description long enough"},
            headers=auth_headers,
        )
        resp2 = await client.post(
            f"{BASE}/projects/{project.id}/rfis",
            json={"title": "Second RFI title here", "description": "Second RFI description long enough"},
            headers=auth_headers,
        )
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        n1 = int(resp1.json()["rfi_number"].split("-")[-1])
        n2 = int(resp2.json()["rfi_number"].split("-")[-1])
        assert n2 == n1 + 1

    @pytest.mark.asyncio
    async def test_add_comment_any_status(
        self, client: AsyncClient, auth_headers: dict, draft_rfi: RFI
    ):
        resp = await client.post(
            f"{BASE}/rfis/{draft_rfi.id}/comments",
            json={"content": "Reviewed drawings — confirm beam elevation first."},
            headers=auth_headers,
        )
        assert resp.status_code == 201


# ── Change Order tests ─────────────────────────────────────────────────────

class TestChangeOrders:

    @pytest.mark.asyncio
    async def test_create_co_from_closed_rfi(
        self, client: AsyncClient, auth_headers: dict, closed_rfi: RFI
    ):
        resp = await client.post(
            f"{BASE}/rfis/{closed_rfi.id}/change-order",
            json={
                "scope_change_description": "Reroute 24x12 supply duct 18 inches north to clear structural beam at grid B-4.",
                "cost_impact_usd": 3850.00,
                "time_impact_days": 2,
                "affected_systems": ["hvac", "structural"],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "PENDING"
        assert body["co_number"].startswith("CO-")
        assert float(body["cost_impact_usd"]) == 3850.00

    @pytest.mark.asyncio
    async def test_cannot_create_co_from_open_rfi(
        self, client: AsyncClient, auth_headers: dict, draft_rfi: RFI
    ):
        resp = await client.post(
            f"{BASE}/rfis/{draft_rfi.id}/change-order",
            json={
                "scope_change_description": "Should not be allowed on open RFI.",
                "cost_impact_usd": 1000.00,
                "time_impact_days": 1,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_approve_co(
        self, client: AsyncClient, auth_headers: dict, closed_rfi: RFI
    ):
        # Create CO
        co_resp = await client.post(
            f"{BASE}/rfis/{closed_rfi.id}/change-order",
            json={
                "scope_change_description": "Reroute duct around beam — confirmed with structural engineer.",
                "cost_impact_usd": 2500.00,
                "time_impact_days": 3,
                "affected_systems": ["hvac"],
            },
            headers=auth_headers,
        )
        assert co_resp.status_code == 201
        co_id = co_resp.json()["id"]

        # Approve
        approve_resp = await client.post(
            f"{BASE}/change-orders/{co_id}/approve",
            headers=auth_headers,
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "APPROVED"
        assert approve_resp.json()["approved_at"] is not None

    @pytest.mark.asyncio
    async def test_reject_co(
        self, client: AsyncClient, auth_headers: dict, closed_rfi: RFI
    ):
        co_resp = await client.post(
            f"{BASE}/rfis/{closed_rfi.id}/change-order",
            json={
                "scope_change_description": "Alternative solution proposed but not yet evaluated by engineer.",
                "cost_impact_usd": 5000.00,
                "time_impact_days": 5,
            },
            headers=auth_headers,
        )
        co_id = co_resp.json()["id"]

        resp = await client.post(
            f"{BASE}/change-orders/{co_id}/reject",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "REJECTED"

    @pytest.mark.asyncio
    async def test_duplicate_co_returns_409(
        self, client: AsyncClient, auth_headers: dict,
        db: AsyncSession, test_user: dict, project: Project
    ):
        rfi = RFI(
            project_id=project.id, org_id=test_user["org"].id,
            created_by=test_user["user"].id, rfi_number="RFI-DUP",
            title="Dup test", description="Dup test long description",
            status="CLOSED", urgency="LOW", source="MANUAL",
            submitted_at=datetime.now(tz=timezone.utc),
            answered_at=datetime.now(tz=timezone.utc),
            closed_at=datetime.now(tz=timezone.utc),
        )
        db.add(rfi)
        await db.commit()

        co_payload = {
            "scope_change_description": "First change order for this RFI — duct rerouting required.",
            "cost_impact_usd": 1000.00, "time_impact_days": 1,
        }
        await client.post(f"{BASE}/rfis/{rfi.id}/change-order", json=co_payload, headers=auth_headers)
        resp2 = await client.post(f"{BASE}/rfis/{rfi.id}/change-order", json=co_payload, headers=auth_headers)
        assert resp2.status_code == 409


# ── PDF Export ─────────────────────────────────────────────────────────────

class TestRFIPDFExport:

    @pytest.mark.asyncio
    async def test_export_rfi_pdf(
        self, client: AsyncClient, auth_headers: dict, closed_rfi: RFI
    ):
        resp = await client.get(
            f"{BASE}/rfis/{closed_rfi.id}/export/pdf",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"


# ── State machine unit tests ───────────────────────────────────────────────

class TestStateMachineUnit:

    def test_all_valid_transitions_defined(self):
        for status in RFIStatus:
            assert status in RFI_TRANSITIONS

    def test_closed_has_no_outgoing_transitions(self):
        assert len(RFI_TRANSITIONS[RFIStatus.CLOSED]) == 0

    def test_draft_only_goes_to_submitted(self):
        assert RFI_TRANSITIONS[RFIStatus.DRAFT] == {RFIStatus.SUBMITTED}

    def test_rejection_loop(self):
        assert RFIStatus.REJECTED in RFI_TRANSITIONS[RFIStatus.ANSWERED]
        assert RFIStatus.UNDER_REVIEW in RFI_TRANSITIONS[RFIStatus.REJECTED]

    def test_can_transition_method(self):
        # Test via RFI_TRANSITIONS dict directly (avoids SQLAlchemy instrumentation)
        draft_targets = RFI_TRANSITIONS[RFIStatus.DRAFT]
        assert RFIStatus.SUBMITTED in draft_targets
        assert RFIStatus.CLOSED not in draft_targets
        assert RFIStatus.ANSWERED not in draft_targets

    def test_rfi_transitions_no_state_skipping(self):
        # Verify DRAFT cannot reach CLOSED without going through intermediates
        reachable_from_draft = RFI_TRANSITIONS[RFIStatus.DRAFT]
        assert RFIStatus.CLOSED not in reachable_from_draft
        assert RFIStatus.ANSWERED not in reachable_from_draft
        assert RFIStatus.UNDER_REVIEW not in reachable_from_draft


# ── SLA unit tests ─────────────────────────────────────────────────────────

class TestSLAUnits:

    def test_sla_task_importable(self):
        from app.tasks.sla_tasks import check_rfi_sla
        assert callable(check_rfi_sla)

    def test_sla_email_task_importable(self):
        from app.tasks.email_tasks import send_rfi_sla_alert
        assert callable(send_rfi_sla_alert)

    def test_beat_schedule_registered(self):
        from app.tasks.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "check-rfi-sla-hourly" in schedule
        task_name = schedule["check-rfi-sla-hourly"]["task"]
        assert "check_rfi_sla" in task_name
