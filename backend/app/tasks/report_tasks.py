"""
Conduit Backend — Report Generation Tasks (M9)
Async PDF/Excel generation via Celery worker-general.

Architecture:
  1. API creates ReportJob (queued) → enqueues this task
  2. Worker loads entities via psycopg2 (sync) + ORM objects
  3. Calls existing exporters (takeoff/rfis modules)
  4. Uploads to S3 via storage helper
  5. Updates job status=completed, publishes Redis event

Bliss Systems LLC — APEX Standard
"""

import io
import uuid as _uuid
from datetime import datetime, timezone

import structlog

from app.core.config import settings
from app.tasks.celery_app import celery_app

logger = structlog.get_logger()


def _sync_db():
    """psycopg2 sync connection for Celery worker context."""
    import psycopg2
    dsn = settings.DATABASE_URL.replace("+asyncpg", "")
    return psycopg2.connect(dsn)


def _update_job(conn, job_id: str, status: str, s3_key: str | None = None,
                error: str | None = None) -> None:
    now = datetime.now(tz=timezone.utc)
    cur = conn.cursor()
    cur.execute(
        """UPDATE report_jobs
           SET status=%s, s3_key=%s, error_message=%s, completed_at=%s
           WHERE id=%s""",
        (status, s3_key, error, now if status in ("completed", "failed") else None, job_id),
    )
    conn.commit()
    cur.close()


def _fetch_org_name(conn, org_id: str) -> str:
    cur = conn.cursor()
    cur.execute("SELECT name FROM organizations WHERE id=%s", (org_id,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else "Conduit"


@celery_app.task(name="app.tasks.report_tasks.generate_report",
                 bind=True, max_retries=2, default_retry_delay=60)
def generate_report(self, job_id: str) -> None:
    conn = None
    try:
        conn = _sync_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT report_type, entity_id, org_id, created_by FROM report_jobs WHERE id=%s",
            (job_id,)
        )
        row = cur.fetchone()
        cur.close()

        if not row:
            logger.error("report_job_not_found", job_id=job_id)
            return

        report_type, entity_id, org_id, created_by = row
        _update_job(conn, job_id, "processing")
        org_name = _fetch_org_name(conn, str(org_id))

        data, filename = _generate(conn, report_type, str(entity_id), org_name)

        from app.core.storage import upload_bytes
        s3_key = f"reports/{org_id}/{job_id}/{filename}"
        upload_bytes(s3_key, data, content_type=_content_type(report_type))

        _update_job(conn, job_id, "completed", s3_key=s3_key)
        logger.info("report_generated", job_id=job_id, type=report_type)

        # Notify user via Redis
        try:
            import asyncio
            import json
            from app.core.redis import redis_client
            if redis_client:
                payload = json.dumps({"type": "report_ready", "job_id": job_id})
                asyncio.run(redis_client.publish(f"ws:user:{created_by}", payload))
        except Exception:
            pass

    except Exception as exc:
        logger.error("report_generation_failed", job_id=job_id, error=str(exc))
        if conn:
            _update_job(conn, job_id, "failed", error=str(exc)[:1000])
        raise self.retry(exc=exc)
    finally:
        if conn:
            conn.close()


def _generate(conn, report_type: str, entity_id: str, org_name: str) -> tuple[bytes, str]:
    if report_type == "takeoff_excel":
        return _gen_takeoff_excel(conn, entity_id, org_name)
    elif report_type == "takeoff_pdf":
        return _gen_takeoff_pdf(conn, entity_id, org_name)
    elif report_type == "rfi_pdf":
        return _gen_rfi_pdf(conn, entity_id, org_name)
    elif report_type == "change_order_pdf":
        return _gen_co_pdf(conn, entity_id, org_name)
    elif report_type == "project_progress":
        return _gen_project_progress(conn, entity_id, org_name)
    else:
        raise ValueError(f"Unknown report type: {report_type}")


def _content_type(report_type: str) -> str:
    if report_type == "takeoff_excel":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/pdf"


# ── Individual generators ──────────────────────────────────────────────────

def _fetch_takeoff(conn, job_id: str):
    """Return lightweight TakeoffJob-like object from raw SQL."""
    from types import SimpleNamespace
    cur = conn.cursor()
    cur.execute(
        """SELECT tj.id, tj.job_number, tj.status, tj.total_cost_usd,
                  tj.approved_by, tj.approved_at, tj.created_at,
                  p.name as project_name
           FROM takeoff_jobs tj
           LEFT JOIN projects p ON p.id = tj.project_id
           WHERE tj.id=%s""",
        (job_id,)
    )
    r = cur.fetchone()

    cur.execute(
        """SELECT item_number, system, component_type, description,
                  quantity, unit, unit_cost_usd, total_cost_usd,
                  manufacturer, model_number, confidence_pct, requires_review
           FROM takeoff_items WHERE job_id=%s ORDER BY system, item_number""",
        (job_id,)
    )
    items_raw = cur.fetchall()
    cur.close()

    if not r:
        raise ValueError(f"TakeoffJob {job_id} not found")

    job = SimpleNamespace(
        id=r[0], job_number=r[1], status=r[2], total_cost_usd=r[3],
        approved_by=r[4], approved_at=r[5], created_at=r[6], project_name=r[7],
    )
    items = [
        SimpleNamespace(
            item_number=i[0], system=i[1], component_type=i[2], description=i[3],
            quantity=i[4], unit=i[5], unit_cost_usd=i[6], total_cost_usd=i[7],
            manufacturer=i[8], model_number=i[9], confidence_pct=i[10],
            requires_review=i[11],
        )
        for i in items_raw
    ]
    return job, items


def _gen_takeoff_excel(conn, entity_id: str, org_name: str) -> tuple[bytes, str]:
    from app.modules.takeoff.exporters import export_excel
    job, items = _fetch_takeoff(conn, entity_id)
    data = export_excel(job, items, org_name)
    return data, f"takeoff_{job.job_number}.xlsx"


def _gen_takeoff_pdf(conn, entity_id: str, org_name: str) -> tuple[bytes, str]:
    from app.modules.takeoff.exporters import export_pdf
    job, items = _fetch_takeoff(conn, entity_id)
    data = export_pdf(job, items, org_name)
    return data, f"takeoff_{job.job_number}.pdf"


def _fetch_rfi(conn, rfi_id: str):
    from types import SimpleNamespace
    cur = conn.cursor()
    cur.execute(
        """SELECT r.id, r.rfi_number, r.title, r.description, r.status,
                  r.urgency, r.source, r.assigned_to, r.markup_id,
                  r.due_date, r.submitted_at, r.answered_at, r.closed_at, r.created_at
           FROM rfis r WHERE r.id=%s""",
        (rfi_id,)
    )
    r = cur.fetchone()

    cur.execute(
        """SELECT id, author_id, content, is_official_response, created_at
           FROM rfi_comments WHERE rfi_id=%s ORDER BY created_at""",
        (rfi_id,)
    )
    comments_raw = cur.fetchall()
    cur.close()

    if not r:
        raise ValueError(f"RFI {rfi_id} not found")

    comments = [
        SimpleNamespace(
            id=c[0], author_id=c[1], content=c[2],
            is_official_response=c[3], created_at=c[4],
        )
        for c in comments_raw
    ]
    rfi = SimpleNamespace(
        id=r[0], rfi_number=r[1], title=r[2], description=r[3], status=r[4],
        urgency=r[5], source=r[6], assigned_to=r[7], markup_id=r[8],
        due_date=r[9], submitted_at=r[10], answered_at=r[11],
        closed_at=r[12], created_at=r[13], comments=comments, change_order=None,
    )
    return rfi


def _gen_rfi_pdf(conn, entity_id: str, org_name: str) -> tuple[bytes, str]:
    from app.modules.rfis.exporter import export_rfi_pdf
    rfi = _fetch_rfi(conn, entity_id)
    data = export_rfi_pdf(rfi, org_name)
    return data, f"RFI-{rfi.rfi_number}.pdf"


def _gen_co_pdf(conn, entity_id: str, org_name: str) -> tuple[bytes, str]:
    """Change Order PDF — uses the same RFI exporter with CO section highlighted."""
    from types import SimpleNamespace
    from app.modules.rfis.exporter import export_rfi_pdf

    cur = conn.cursor()
    cur.execute(
        """SELECT co.id, co.co_number, co.scope_change_description,
                  co.cost_impact_usd, co.time_impact_days, co.status,
                  co.approved_at, co.rfi_id
           FROM change_orders co WHERE co.id=%s""",
        (entity_id,)
    )
    r = cur.fetchone()
    cur.close()

    if not r:
        raise ValueError(f"ChangeOrder {entity_id} not found")

    rfi = _fetch_rfi(conn, str(r[7]))
    rfi.change_order = SimpleNamespace(
        id=r[0], co_number=r[1], scope_change_description=r[2],
        cost_impact_usd=r[3], time_impact_days=r[4], status=r[5], approved_at=r[6],
    )
    data = export_rfi_pdf(rfi, org_name)
    return data, f"CO-{r[1]}.pdf"


def _gen_project_progress(conn, entity_id: str, org_name: str) -> tuple[bytes, str]:
    """Project progress report: zone stats + recent RFIs summary."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    cur = conn.cursor()
    cur.execute("SELECT name FROM projects WHERE id=%s", (entity_id,))
    proj_row = cur.fetchone()
    project_name = proj_row[0] if proj_row else "Unknown Project"

    cur.execute(
        """SELECT status, COUNT(*) as cnt
           FROM work_zones WHERE project_id=%s AND deleted_at IS NULL
           GROUP BY status""",
        (entity_id,)
    )
    zone_counts = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute(
        """SELECT rfi_number, title, status, urgency, created_at
           FROM rfis WHERE project_id=%s AND deleted_at IS NULL
           ORDER BY created_at DESC LIMIT 10""",
        (entity_id,)
    )
    rfis = cur.fetchall()
    cur.close()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                             leftMargin=0.75*inch, rightMargin=0.75*inch,
                             topMargin=inch, bottomMargin=0.75*inch)
    styles = getSampleStyleSheet()
    story = []

    # Header
    story.append(Paragraph(f"<b>{org_name}</b>", styles["Heading1"]))
    story.append(Paragraph("Project Progress Report", styles["Heading2"]))
    story.append(Paragraph(f"Project: {project_name}", styles["Normal"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1E3A5F")))
    story.append(Spacer(1, 0.2*inch))

    # Zone Summary
    story.append(Paragraph("<b>Field Zone Status</b>", styles["Heading3"]))
    total = sum(zone_counts.values())
    completed = zone_counts.get("COMPLETED", 0)
    pct = round(completed / total * 100, 1) if total else 0

    zone_data = [["Status", "Count", "% of Total"]]
    for status in ("COMPLETED", "IN_PROGRESS", "BLOCKED", "NOT_STARTED"):
        cnt = zone_counts.get(status, 0)
        zone_data.append([status, str(cnt),
                          f"{round(cnt/total*100, 1)}%" if total else "0%"])
    zone_data.append(["TOTAL", str(total), f"{pct}% Complete"])

    tbl = Table(zone_data, colWidths=[2.5*inch, inch, 1.5*inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F5F5F5")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8F0FE")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.3*inch))

    # Recent RFIs
    if rfis:
        story.append(Paragraph("<b>Recent RFIs (last 10)</b>", styles["Heading3"]))
        rfi_data = [["RFI#", "Title", "Status", "Urgency", "Date"]]
        for r in rfis:
            rfi_data.append([
                r[0], r[1][:40] + ("…" if len(r[1]) > 40 else ""),
                r[2], r[3], r[4].strftime("%Y-%m-%d") if r[4] else "",
            ])
        rfi_tbl = Table(rfi_data, colWidths=[0.8*inch, 3*inch, inch, 0.8*inch, 0.9*inch])
        rfi_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(rfi_tbl)

    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(
        f"<i>Generated by Conduit — {org_name} — {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</i>",
        styles["Normal"],
    ))

    doc.build(story)
    return buf.getvalue(), f"progress_{entity_id[:8]}.pdf"
