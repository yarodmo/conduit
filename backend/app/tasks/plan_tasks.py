"""
Conduit Backend — Plan Processing Celery Tasks (M3)
5-step pipeline: normalize → extract pages → analyze → generate tiles → notify

All heavy I/O (OpenCV, PyMuPDF, Tesseract) runs inside Celery workers,
never blocking the API process.

Bliss Systems LLC — APEX Standard
"""

import io
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from celery import chain, shared_task

from app.core.config import settings
from app.core.storage import (
    download_bytes,
    plan_original_key,
    plan_page_full_key,
    plan_page_thumb_key,
    plan_tile_key,
    upload_bytes,
)
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
TILE_SIZE = 256
ZOOM_LEVELS = 4        # 0 = overview, 3 = highest detail
THUMB_WIDTH = 400
FULL_DPI = 300
PLAN_KEYWORDS = {
    "hvac": ["hvac", "duct", "mechanical", "supply", "return", "exhaust", "vav", "ahu", "mech"],
    "electrical": ["electrical", "panel", "circuit", "elec", "power", "lighting"],
    "plumbing": ["plumbing", "plumb", "sanitary", "drain", "water", "fixture"],
    "fire_protection": ["fire", "sprinkler", "suppression"],
    "mep": ["mep"],
}


# ── Sync DB helper (runs inside Celery, no async) ──────────────────────────

def _sync_db():
    """Create a synchronous SQLAlchemy session for Celery tasks."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = sa.create_engine(url, pool_pre_ping=True)
    return Session(engine)


def _update_job(session: Any, job_id: str, **kwargs: Any) -> None:
    """Update a PlanProcessingJob row."""
    from app.models.plans import PlanProcessingJob
    job = session.get(PlanProcessingJob, uuid.UUID(job_id))
    if job:
        for k, v in kwargs.items():
            setattr(job, k, v)
        session.commit()


def _update_plan(session: Any, plan_id: str, **kwargs: Any) -> None:
    from app.models.plans import Plan
    plan = session.get(Plan, uuid.UUID(plan_id))
    if plan:
        for k, v in kwargs.items():
            setattr(plan, k, v)
        session.commit()


# ── STEP 1 — Photo Normalization (OpenCV) ─────────────────────────────────

@celery_app.task(
    name="app.tasks.plan_tasks.normalize_photo",
    bind=True,
    max_retries=2,
    queue="plans",
)
def normalize_photo(
    self,
    plan_id: str,
    job_id: str,
    org_id: str,
    project_id: str,
    source_type: str,
) -> dict[str, Any]:
    """
    STEP 1 — Deskew + enhance photos from phones.
    Only applies when source_type in (phone_photo, camera_direct, scan).
    PDFs pass through unchanged.
    """
    result = {
        "plan_id": plan_id,
        "job_id": job_id,
        "org_id": org_id,
        "project_id": project_id,
        "source_type": source_type,
        "deskew_applied": False,
    }

    photo_types = {"phone_photo", "camera_direct", "scan"}
    if source_type not in photo_types:
        logger.info("normalize_photo: skipped (source=%s)", source_type)
        return result

    session = _sync_db()
    try:
        _update_job(session, job_id, current_step="normalizing_photo", progress_pct=5)

        import cv2
        import numpy as np
        from PIL import Image

        # Detect file extension from S3 original
        ext = "jpg"
        key = plan_original_key(org_id, project_id, plan_id, ext)
        raw = download_bytes(settings.S3_BUCKET_PLANS, key)
        img_arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)

        if img is None:
            logger.warning("normalize_photo: could not decode image for plan %s", plan_id)
            return result

        # Perspective correction — find the largest quadrilateral (plan paper)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 75, 200)

        contours, _ = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

        plan_contour = None
        for c in contours:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) == 4:
                plan_contour = approx
                break

        if plan_contour is not None:
            pts = plan_contour.reshape(4, 2).astype(np.float32)
            # Order: top-left, top-right, bottom-right, bottom-left
            s = pts.sum(axis=1)
            diff = np.diff(pts, axis=1)
            ordered = np.zeros((4, 2), dtype=np.float32)
            ordered[0] = pts[np.argmin(s)]
            ordered[2] = pts[np.argmax(s)]
            ordered[1] = pts[np.argmin(diff)]
            ordered[3] = pts[np.argmax(diff)]

            w = int(max(
                np.linalg.norm(ordered[0] - ordered[1]),
                np.linalg.norm(ordered[2] - ordered[3]),
            ))
            h = int(max(
                np.linalg.norm(ordered[0] - ordered[3]),
                np.linalg.norm(ordered[1] - ordered[2]),
            ))

            if w > 100 and h > 100:
                dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
                M = cv2.getPerspectiveTransform(ordered, dst)
                img = cv2.warpPerspective(img, M, (w, h))
                result["deskew_applied"] = True

        # Enhance contrast for OCR
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)
        img = cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)

        # Quality score — based on Laplacian variance (sharpness)
        gray2 = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        fm = cv2.Laplacian(gray2, cv2.CV_64F).var()
        quality_score = min(100, int(fm / 10))

        # Re-upload normalized image
        _, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        upload_bytes(buf.tobytes(), settings.S3_BUCKET_PLANS, key, "image/jpeg")

        _update_plan(session, plan_id, deskew_applied=result["deskew_applied"],
                     quality_score=quality_score)
        _update_job(session, job_id, progress_pct=15)

        result["quality_score"] = quality_score
    except Exception as exc:
        logger.exception("normalize_photo failed: %s", exc)
        _update_job(session, job_id, status="failed",
                    error_message=f"normalization: {exc}")
        raise self.retry(exc=exc, countdown=10)
    finally:
        session.close()

    return result


# ── STEP 2 — Page Extraction (PyMuPDF) ────────────────────────────────────

@celery_app.task(
    name="app.tasks.plan_tasks.extract_pages",
    bind=True,
    max_retries=2,
    queue="plans",
)
def extract_pages(self, prev_result: dict[str, Any]) -> dict[str, Any]:
    """
    STEP 2 — Render each page to PNG at 300 DPI + generate thumbnails.
    Works for both PDF and images.
    """
    plan_id = prev_result["plan_id"]
    job_id = prev_result["job_id"]
    org_id = prev_result["org_id"]
    project_id = prev_result["project_id"]
    source_type = prev_result["source_type"]

    session = _sync_db()
    try:
        _update_job(session, job_id, current_step="extracting_pages",
                    status="processing", progress_pct=20,
                    started_at=datetime.now(tz=timezone.utc))

        pages_info: list[dict[str, Any]] = []
        is_pdf = source_type == "pdf"

        if is_pdf:
            import fitz  # PyMuPDF

            ext = "pdf"
            key = plan_original_key(org_id, project_id, plan_id, ext)
            raw = download_bytes(settings.S3_BUCKET_PLANS, key)

            doc = fitz.open(stream=raw, filetype="pdf")
            total_pages = len(doc)

            for page_num in range(total_pages):
                page = doc[page_num]
                mat = fitz.Matrix(FULL_DPI / 72, FULL_DPI / 72)
                pix = page.get_pixmap(matrix=mat)
                png_bytes = pix.tobytes("png")

                # Upload full-res page
                full_key = plan_page_full_key(org_id, project_id, plan_id, page_num + 1)
                upload_bytes(png_bytes, settings.S3_BUCKET_PLANS, full_key, "image/png")

                # Generate thumbnail
                from PIL import Image
                img = Image.open(io.BytesIO(png_bytes))
                w, h = img.size
                ratio = THUMB_WIDTH / w
                thumb = img.resize((THUMB_WIDTH, int(h * ratio)), Image.LANCZOS)
                thumb_buf = io.BytesIO()
                thumb.save(thumb_buf, format="JPEG", quality=85)

                thumb_key = plan_page_thumb_key(org_id, project_id, plan_id, page_num + 1)
                upload_bytes(thumb_buf.getvalue(), settings.S3_BUCKET_PLANS, thumb_key, "image/jpeg")

                orientation = "landscape" if w > h else "portrait"
                pages_info.append({
                    "page_number": page_num + 1,
                    "s3_key_full": full_key,
                    "s3_key_thumb": thumb_key,
                    "width_px": w,
                    "height_px": h,
                    "orientation": orientation,
                })

                progress = 20 + int((page_num + 1) / total_pages * 20)
                _update_job(session, job_id, progress_pct=progress)

            doc.close()

        else:
            # Single image (phone photo / scan) — already normalized in STEP 1
            from PIL import Image

            ext = "jpg"
            key = plan_original_key(org_id, project_id, plan_id, ext)
            raw = download_bytes(settings.S3_BUCKET_PLANS, key)
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            w, h = img.size

            # Save as full-res PNG
            png_buf = io.BytesIO()
            img.save(png_buf, format="PNG")
            full_key = plan_page_full_key(org_id, project_id, plan_id, 1)
            upload_bytes(png_buf.getvalue(), settings.S3_BUCKET_PLANS, full_key, "image/png")

            ratio = THUMB_WIDTH / w
            thumb = img.resize((THUMB_WIDTH, int(h * ratio)), Image.LANCZOS)
            thumb_buf = io.BytesIO()
            thumb.save(thumb_buf, format="JPEG", quality=85)
            thumb_key = plan_page_thumb_key(org_id, project_id, plan_id, 1)
            upload_bytes(thumb_buf.getvalue(), settings.S3_BUCKET_PLANS, thumb_key, "image/jpeg")

            total_pages = 1
            pages_info.append({
                "page_number": 1,
                "s3_key_full": full_key,
                "s3_key_thumb": thumb_key,
                "width_px": w,
                "height_px": h,
                "orientation": "landscape" if w > h else "portrait",
            })

        # Persist page records
        from app.models.plans import PlanPage
        for info in pages_info:
            page_rec = PlanPage(
                plan_id=uuid.UUID(plan_id),
                **info,
            )
            session.add(page_rec)

        _update_plan(session, plan_id, total_pages=total_pages)
        _update_job(session, job_id, progress_pct=40)
        session.commit()

    except Exception as exc:
        logger.exception("extract_pages failed: %s", exc)
        _update_job(session, job_id, status="failed",
                    error_message=f"page extraction: {exc}")
        raise self.retry(exc=exc, countdown=15)
    finally:
        session.close()

    return {**prev_result, "total_pages": total_pages, "pages": pages_info}


# ── STEP 3 — Analysis (OCR + type detection) ──────────────────────────────

@celery_app.task(
    name="app.tasks.plan_tasks.analyze_plan",
    bind=True,
    max_retries=2,
    queue="plans",
)
def analyze_plan(self, prev_result: dict[str, Any]) -> dict[str, Any]:
    """
    STEP 3 — OCR first page, detect plan type, scale, metadata.
    """
    plan_id = prev_result["plan_id"]
    job_id = prev_result["job_id"]
    org_id = prev_result["org_id"]
    project_id = prev_result["project_id"]
    pages = prev_result.get("pages", [])

    session = _sync_db()
    analysis: dict[str, Any] = {}
    try:
        _update_job(session, job_id, current_step="analyzing", progress_pct=45)

        if not pages:
            _update_job(session, job_id, progress_pct=60)
            return {**prev_result, "analysis": analysis}

        # OCR first page only (fast — full OCR during M5 takeoff)
        first_page_key = pages[0]["s3_key_full"]
        raw = download_bytes(settings.S3_BUCKET_PLANS, first_page_key)

        try:
            import pytesseract
            from PIL import Image

            img = Image.open(io.BytesIO(raw)).convert("RGB")
            # Scale down for faster OCR (150 DPI equivalent)
            if img.width > 2000:
                ratio = 1500 / img.width
                img = img.resize((1500, int(img.height * ratio)), Image.LANCZOS)

            ocr_text = pytesseract.image_to_string(img, config="--psm 3")
        except Exception:
            ocr_text = ""

        # Detect plan type from OCR text
        text_lower = ocr_text.lower()
        detected_type = "unknown"
        for ptype, keywords in PLAN_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                detected_type = ptype
                break

        # Detect scale pattern: "1/8" = 1'-0"" or "1:50" etc.
        scale_match = re.search(
            r'(\d+/\d+["\']?\s*=\s*\d+[\'"-]\d*["\']?|\d+:\d+)', ocr_text
        )
        scale_text = scale_match.group(0).strip() if scale_match else None

        # Detect plan number (common patterns: "A-101", "M-1", "E-2.1")
        num_match = re.search(r'\b([A-Z]{1,3}-\d{1,3}(?:\.\d)?)\b', ocr_text)
        plan_number = num_match.group(1) if num_match else None

        # Complexity: count of distinct elements (rough proxy via word count)
        word_count = len(ocr_text.split())
        if word_count < 200:
            complexity = "simple"
        elif word_count < 800:
            complexity = "standard"
        else:
            complexity = "complex"

        analysis = {
            "plan_type": detected_type,
            "scale_text": scale_text,
            "plan_number": plan_number,
            "complexity_score": complexity,
        }

        # Persist OCR text on first page record
        from app.models.plans import PlanPage
        from sqlalchemy import select
        stmt = select(PlanPage).where(
            PlanPage.plan_id == uuid.UUID(plan_id),
            PlanPage.page_number == 1,
        )
        page_rec = session.execute(stmt).scalar_one_or_none()
        if page_rec:
            page_rec.ocr_text = ocr_text[:50000]  # cap at 50k chars
            session.commit()

        _update_plan(session, plan_id, **analysis)
        _update_job(session, job_id, progress_pct=60)

    except Exception as exc:
        logger.exception("analyze_plan failed: %s", exc)
        # Non-fatal — analysis failure should not stop tile generation
        _update_job(session, job_id, current_step="analysis_warning",
                    error_message=f"analysis partial: {exc}")
    finally:
        session.close()

    return {**prev_result, "analysis": analysis}


# ── STEP 4 — Tile Generation ───────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.plan_tasks.generate_tiles",
    bind=True,
    max_retries=2,
    queue="plans",
)
def generate_tiles(self, prev_result: dict[str, Any]) -> dict[str, Any]:
    """
    STEP 4 — Build WebP tile pyramid (4 zoom levels) for the plan viewer.
    Tiles are 256×256 px, stored at tiles/{plan_id}/{page}/{z}/{x}/{y}.webp
    Pre-generates zoom 0 and 1; higher zooms are on-demand.
    """
    plan_id = prev_result["plan_id"]
    job_id = prev_result["job_id"]
    org_id = prev_result["org_id"]
    project_id = prev_result["project_id"]
    pages = prev_result.get("pages", [])

    session = _sync_db()
    try:
        _update_job(session, job_id, current_step="generating_tiles", progress_pct=65)

        from PIL import Image

        total = len(pages)
        for idx, page_info in enumerate(pages):
            page_num = page_info["page_number"]
            raw = download_bytes(settings.S3_BUCKET_PLANS, page_info["s3_key_full"])
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            orig_w, orig_h = img.size

            # Pre-generate zoom levels 0 and 1 eagerly; 2+ are generated on-demand
            for zoom in range(2):
                scale = 2 ** zoom  # zoom 0 = 1x, zoom 1 = 2x (more tiles)
                # At zoom level z: the image is divided into a grid of 2^z × 2^z tiles
                # Each tile covers (orig_w / 2^z) × (orig_h / 2^z) px of original
                cols = 2 ** zoom
                rows = 2 ** zoom
                tile_w = orig_w // cols if cols else orig_w
                tile_h = orig_h // rows if rows else orig_h

                for row in range(rows):
                    for col in range(cols):
                        left = col * tile_w
                        upper = row * tile_h
                        right = min(left + tile_w, orig_w)
                        lower = min(upper + tile_h, orig_h)

                        tile = img.crop((left, upper, right, lower))
                        tile = tile.resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS)

                        buf = io.BytesIO()
                        tile.save(buf, format="WEBP", quality=85, method=4)

                        key = plan_tile_key(plan_id, page_num, zoom, col, row)
                        upload_bytes(buf.getvalue(), settings.S3_BUCKET_PLANS, key, "image/webp")

            progress = 65 + int((idx + 1) / total * 25)
            _update_job(session, job_id, progress_pct=progress)

    except Exception as exc:
        logger.exception("generate_tiles failed: %s", exc)
        _update_job(session, job_id, status="failed",
                    error_message=f"tile generation: {exc}")
        raise self.retry(exc=exc, countdown=15)
    finally:
        session.close()

    return prev_result


# ── STEP 5 — Finalize + Notify ─────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.plan_tasks.finalize_plan",
    queue="plans",
)
def finalize_plan(prev_result: dict[str, Any]) -> None:
    """
    STEP 5 — Mark plan as ready, update job, push WebSocket notification.
    """
    plan_id = prev_result["plan_id"]
    job_id = prev_result["job_id"]

    session = _sync_db()
    try:
        now = datetime.now(tz=timezone.utc)
        _update_plan(session, plan_id, status="ready")
        _update_job(
            session, job_id,
            status="ready",
            current_step="complete",
            progress_pct=100,
            completed_at=now,
        )

        # Redis pub/sub notification for WebSocket clients
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL)
        r.publish(
            f"plan:{plan_id}:status",
            json.dumps({"plan_id": plan_id, "status": "ready", "progress_pct": 100}),
        )
        logger.info("plan_processing_complete plan_id=%s", plan_id)

    except Exception as exc:
        logger.exception("finalize_plan failed: %s", exc)
        _update_job(session, job_id, status="failed",
                    error_message=f"finalize: {exc}")
    finally:
        session.close()


# ── Entry point — chains all 5 steps ──────────────────────────────────────

def dispatch_plan_processing(
    plan_id: str,
    job_id: str,
    org_id: str,
    project_id: str,
    source_type: str,
) -> str:
    """
    Dispatch the full processing pipeline as a Celery chain.
    Returns the Celery task group ID.
    """
    initial = {
        "plan_id": plan_id,
        "job_id": job_id,
        "org_id": org_id,
        "project_id": project_id,
        "source_type": source_type,
    }

    pipeline = chain(
        normalize_photo.s(plan_id, job_id, org_id, project_id, source_type),
        extract_pages.s(),
        analyze_plan.s(),
        generate_tiles.s(),
        finalize_plan.s(),
    )
    result = pipeline.apply_async()
    return result.id


# ── On-demand tile generation (high zoom levels) ──────────────────────────

@celery_app.task(
    name="app.tasks.plan_tasks.generate_tile_on_demand",
    queue="plans",
)
def generate_tile_on_demand(
    plan_id: str,
    org_id: str,
    project_id: str,
    page: int,
    zoom: int,
    x: int,
    y: int,
) -> bool:
    """Generate a single tile for zoom > 1 (on-demand). Returns True on success."""
    session = _sync_db()
    try:
        from PIL import Image
        from app.models.plans import PlanPage
        from sqlalchemy import select

        stmt = select(PlanPage).where(
            PlanPage.plan_id == uuid.UUID(plan_id),
            PlanPage.page_number == page,
        )
        page_rec = session.execute(stmt).scalar_one_or_none()
        if not page_rec or not page_rec.s3_key_full:
            return False

        raw = download_bytes(settings.S3_BUCKET_PLANS, page_rec.s3_key_full)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        orig_w, orig_h = img.size

        cols = 2 ** zoom
        rows = 2 ** zoom
        tile_w = orig_w // cols
        tile_h = orig_h // rows

        left = x * tile_w
        upper = y * tile_h
        right = min(left + tile_w, orig_w)
        lower = min(upper + tile_h, orig_h)

        if left >= orig_w or upper >= orig_h:
            return False

        tile = img.crop((left, upper, right, lower))
        tile = tile.resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS)

        buf = io.BytesIO()
        tile.save(buf, format="WEBP", quality=85)

        key = plan_tile_key(plan_id, page, zoom, x, y)
        upload_bytes(buf.getvalue(), settings.S3_BUCKET_PLANS, key, "image/webp")
        return True

    except Exception as exc:
        logger.exception("generate_tile_on_demand failed: %s", exc)
        return False
    finally:
        session.close()
