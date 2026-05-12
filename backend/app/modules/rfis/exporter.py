"""
Conduit Backend — RFI PDF Exporter (M7)
Professional RFI document with org header, full state timeline, and CO summary.
This PDF is the legal document presented to the project owner.

Bliss Systems LLC — APEX Standard
"""

import io
from typing import Any


def export_rfi_pdf(rfi: Any, org_name: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                             leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                             topMargin=0.75 * inch, bottomMargin=0.75 * inch)

    styles = getSampleStyleSheet()
    BLUE = colors.HexColor("#1F4E79")

    title_s = ParagraphStyle("T", parent=styles["Heading1"], textColor=BLUE, fontSize=16)
    sub_s = ParagraphStyle("S", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
    section_s = ParagraphStyle("Sec", parent=styles["Heading2"], textColor=BLUE,
                                fontSize=11, spaceBefore=10, spaceAfter=4)
    body_s = ParagraphStyle("B", parent=styles["Normal"], fontSize=9, leading=14)

    URGENCY_COLORS = {
        "LOW": colors.HexColor("#28a745"),
        "MEDIUM": colors.HexColor("#ffc107"),
        "HIGH": colors.HexColor("#fd7e14"),
        "CRITICAL": colors.HexColor("#dc3545"),
    }
    urgency_color = URGENCY_COLORS.get(rfi.urgency, colors.grey)

    story = []

    # ── Header ──────────────────────────────────────────────────────────
    story.append(Paragraph(f"Request for Information — {rfi.rfi_number}", title_s))
    story.append(Paragraph(f"{org_name}  ·  Status: {rfi.status}", sub_s))
    story.append(HRFlowable(width="100%", thickness=2, color=BLUE, spaceAfter=8))

    # ── Metadata table ──────────────────────────────────────────────────
    urgency_para = Paragraph(
        f'<font color="{urgency_color.hexval()}"><b>{rfi.urgency}</b></font>',
        body_s,
    )
    meta = [
        ["Title:", rfi.title],
        ["Status:", rfi.status],
        ["Urgency:", rfi.urgency],
        ["Source:", rfi.source],
        ["Due Date:", str(rfi.due_date.date()) if rfi.due_date else "—"],
        ["Created:", str(rfi.created_at.date())],
    ]
    meta_table = Table(meta, colWidths=[1.5 * inch, 5.5 * inch])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EBF3FB")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F9F9F9")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.15 * inch))

    # ── Description ─────────────────────────────────────────────────────
    story.append(Paragraph("Description", section_s))
    story.append(Paragraph(rfi.description, body_s))

    # ── Timeline ────────────────────────────────────────────────────────
    story.append(Paragraph("Status Timeline", section_s))
    timeline_data = [["Event", "Date", "Details"]]
    timeline_data.append(["Created", str(rfi.created_at.strftime("%Y-%m-%d %H:%M")), ""])
    if rfi.submitted_at:
        timeline_data.append(["Submitted", str(rfi.submitted_at.strftime("%Y-%m-%d %H:%M")), ""])
    if rfi.answered_at:
        timeline_data.append(["Answered", str(rfi.answered_at.strftime("%Y-%m-%d %H:%M")), ""])
    if rfi.closed_at:
        timeline_data.append(["Closed", str(rfi.closed_at.strftime("%Y-%m-%d %H:%M")), ""])

    tl_table = Table(timeline_data, colWidths=[1.5 * inch, 2 * inch, 3.5 * inch])
    tl_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9F9F9")]),
    ]))
    story.append(tl_table)

    # ── Comments / Official Responses ────────────────────────────────────
    official = [c for c in rfi.comments if c.is_official_response]
    if official:
        story.append(Paragraph("Official Responses", section_s))
        for c in official:
            story.append(Paragraph(
                f"<b>{c.created_at.strftime('%Y-%m-%d')}</b> — {c.content}", body_s
            ))
            story.append(Spacer(1, 0.05 * inch))

    # ── Change Order summary ─────────────────────────────────────────────
    if rfi.change_order:
        co = rfi.change_order
        story.append(Paragraph("Change Order", section_s))
        co_data = [
            ["CO Number:", co.co_number],
            ["Status:", co.status],
            ["Cost Impact:", f"${float(co.cost_impact_usd):,.2f}"],
            ["Time Impact:", f"{co.time_impact_days} days"],
            ["Systems:", ", ".join(co.affected_systems or [])],
        ]
        co_table = Table(co_data, colWidths=[1.5 * inch, 5.5 * inch])
        co_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#FFF3CD")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ]))
        story.append(co_table)
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(co.scope_change_description, body_s))

    # ── Footer ───────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.3 * inch))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Paragraph(
        f"Generated by Conduit — MEP Intelligence. Connected. | {org_name}",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7, textColor=colors.grey),
    ))

    doc.build(story)
    return buf.getvalue()
