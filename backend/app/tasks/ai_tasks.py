"""
Conduit Backend — AI Takeoff Tasks (M5)
5-phase Celery pipeline: preprocess → section → analyze → postprocess → finalize

All Claude API calls are async-safe via Celery + exponential backoff.
Cost shown to user BEFORE execution. Raw response always persisted.

Bliss Systems LLC — APEX Standard
"""

import io
import json
import logging
import math
import random
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
PROMPT_DIR = Path(__file__).parent.parent.parent / "ai_prompts" / "takeoff"
SECTION_MAX_PX = 2000          # split if plan page wider than this
SECTION_OVERLAP = 0.15         # 15% overlap between sections
TILE_SIZE_FOR_AI = 1024        # resize section to this before sending to Claude
LOW_CONFIDENCE_THRESHOLD = 30  # items below this → requires_review = True

# Claude pricing (claude-sonnet-4-5, per million tokens, May 2026)
COST_PER_M_INPUT = 3.0
COST_PER_M_OUTPUT = 15.0
TOKENS_PER_IMAGE = 1600        # approximate for 1024px image
TOKENS_PER_PROMPT = 2000       # prompt template tokens


# ── DB helper (sync, for Celery) ───────────────────────────────────────────

def _sync_db():
    import sqlalchemy as sa
    from sqlalchemy.orm import Session
    from app.core.config import settings
    url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = sa.create_engine(url, pool_pre_ping=True)
    return Session(engine)


def _update_job(session: Any, job_id: str, **kwargs: Any) -> None:
    from app.models.takeoff import TakeoffJob
    job = session.get(TakeoffJob, uuid.UUID(job_id))
    if job:
        for k, v in kwargs.items():
            setattr(job, k, v)
        session.commit()


# ── Cost estimation ────────────────────────────────────────────────────────

def estimate_cost(width_px: int, height_px: int) -> dict[str, Any]:
    """Estimate Claude API cost before dispatching the takeoff."""
    n_sections = max(1, math.ceil(width_px / SECTION_MAX_PX))
    input_tokens = n_sections * (TOKENS_PER_IMAGE + TOKENS_PER_PROMPT)
    output_tokens = n_sections * 800   # average output per section
    cost = (input_tokens * COST_PER_M_INPUT + output_tokens * COST_PER_M_OUTPUT) / 1_000_000
    return {
        "sections": n_sections,
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_cost_usd": round(cost, 4),
    }


# ── PHASE 1+2 — Section & Analyze ─────────────────────────────────────────

def _load_prompt(version: str = "v1") -> str:
    path = PROMPT_DIR / f"mep-takeoff-{version}.txt"
    return path.read_text(encoding="utf-8")


def _call_claude_with_backoff(
    prompt: str,
    image_b64: str,
    model: str,
    max_retries: int = 3,
) -> tuple[dict[str, Any], float]:
    """Call Claude Vision via litellm with exponential backoff. Returns (parsed_json, cost_usd)."""
    import litellm

    messages = [{
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_b64}"},
            },
            {"type": "text", "text": prompt},
        ],
    }]

    for attempt in range(max_retries):
        try:
            response = litellm.completion(
                model=model,
                messages=messages,
                max_tokens=4096,
            )

            text = response.choices[0].message.content
            parsed = json.loads(text)

            input_t = response.usage.prompt_tokens
            output_t = response.usage.completion_tokens
            cost = (input_t * COST_PER_M_INPUT + output_t * COST_PER_M_OUTPUT) / 1_000_000

            return parsed, cost

        except (json.JSONDecodeError, KeyError, AttributeError):
            logger.warning("Claude returned invalid JSON on attempt %d", attempt + 1)
            if attempt == max_retries - 1:
                raise
        except Exception as exc:
            if attempt == max_retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            logger.warning("Claude API error attempt %d, retry in %.1fs: %s", attempt + 1, wait, exc)
            time.sleep(wait)

    raise RuntimeError("Claude API failed after all retries")


def _crop_section(img_bytes: bytes, section_idx: int, n_sections: int, overlap: float) -> bytes:
    """Crop a section of the plan image with overlap."""
    from PIL import Image

    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = img.size
    section_w = w / n_sections
    overlap_px = int(section_w * overlap)

    left = max(0, int(section_idx * section_w) - overlap_px)
    right = min(w, int((section_idx + 1) * section_w) + overlap_px)

    crop = img.crop((left, 0, right, h))
    crop = crop.resize((TILE_SIZE_FOR_AI, int(h * TILE_SIZE_FOR_AI / (right - left))), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    return buf.getvalue()


def _dedup_overlap_items(all_items: list[dict], n_sections: int) -> list[dict]:
    """Remove duplicate items detected in overlap zones between sections."""
    if n_sections <= 1:
        return all_items

    seen: dict[str, dict] = {}
    for item in all_items:
        # Key: type + tag (if available) or specification prefix
        key = f"{item['type']}:{item.get('tag') or item['specification'][:40]}"
        if key not in seen or item.get("confidence", 0) > seen[key].get("confidence", 0):
            seen[key] = item

    return list(seen.values())


# ── Main Celery task ───────────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.ai_tasks.run_takeoff_analysis",
    bind=True,
    max_retries=2,
    queue="ai",
    time_limit=600,
)
def run_takeoff_analysis(
    self,
    job_id: str,
    plan_id: str,
    org_id: str,
    project_id: str,
    page: int = 1,
) -> None:
    """
    Full M5 pipeline for one plan page:
      1. Fetch page image from S3
      2. Split into sections if > SECTION_MAX_PX wide
      3. Call Claude Vision on each section (with backoff)
      4. Deduplicate overlap items
      5. Validate with Pydantic, cross with catalog, compute costs
      6. Persist items + finalize job
    """
    from app.core.config import settings
    from app.core.storage import download_bytes
    from app.models.plans import Plan, PlanPage
    from app.models.takeoff import MaterialCatalog, TakeoffItem, TakeoffJob

    import base64
    import sqlalchemy as sa

    session = _sync_db()
    try:
        job = session.get(TakeoffJob, uuid.UUID(job_id))
        if not job:
            logger.error("takeoff job %s not found", job_id)
            return

        _update_job(session, job_id, status="processing")

        # Load plan page
        stmt = sa.select(PlanPage).where(
            PlanPage.plan_id == uuid.UUID(plan_id),
            PlanPage.page_number == page,
        )
        plan_page = session.execute(stmt).scalar_one_or_none()
        if not plan_page or not plan_page.s3_key_full:
            raise RuntimeError(f"Plan page {page} not found or not processed")

        img_bytes = download_bytes(settings.S3_BUCKET_PLANS, plan_page.s3_key_full)
        width_px = plan_page.width_px or SECTION_MAX_PX
        height_px = plan_page.height_px or 3300

        # Load plan context
        plan = session.get(Plan, uuid.UUID(plan_id))
        color_legend = json.dumps(plan.color_legend or {})
        scale = plan.scale_text or "unknown"
        plan_type = plan.plan_type or "unknown"

        # Build prompt
        prompt_template = _load_prompt(job.prompt_version)
        prompt = (prompt_template
                  .replace("{project_type}", "commercial")
                  .replace("{plan_type}", plan_type)
                  .replace("{detected_scale}", scale)
                  .replace("{color_legend_json}", color_legend)
                  .replace("{quality_score}", str(plan.quality_score or 80)))

        model = settings.DEFAULT_AI_MODEL
        n_sections = max(1, math.ceil(width_px / SECTION_MAX_PX))

        _update_job(session, job_id, total_sections=n_sections, model_version=model)

        all_raw: list[dict] = []
        total_cost = 0.0

        for idx in range(n_sections):
            section_bytes = _crop_section(img_bytes, idx, n_sections, SECTION_OVERLAP)
            img_b64 = base64.b64encode(section_bytes).decode()

            section_result, section_cost = _call_claude_with_backoff(prompt, img_b64, model)
            total_cost += section_cost

            components = section_result.get("components", [])
            for c in components:
                c["section_index"] = idx

            all_raw.extend(components)
            _update_job(session, job_id,
                        sections_completed=idx + 1,
                        actual_cost_usd=round(total_cost, 4))

        # Dedup + validate
        deduped = _dedup_overlap_items(all_raw, n_sections)

        # Cross with material catalog
        catalog_map: dict[str, MaterialCatalog] = {}
        catalog_rows = session.execute(
            sa.select(MaterialCatalog).where(
                sa.or_(
                    MaterialCatalog.org_id == uuid.UUID(org_id),
                    MaterialCatalog.org_id.is_(None),
                ),
                MaterialCatalog.is_active.is_(True),
            )
        ).scalars().all()
        for row in catalog_rows:
            catalog_map[f"{row.item_type}:{row.specification[:30].lower()}"] = row

        total_material_cost = Decimal("0")
        items_to_insert = []
        for comp in deduped:
            confidence = int(comp.get("confidence", 100))
            requires_review = confidence < LOW_CONFIDENCE_THRESHOLD

            # Try catalog match
            spec_key = f"{comp['type']}:{comp.get('specification', '')[:30].lower()}"
            catalog_match = catalog_map.get(spec_key)

            qty = Decimal(str(comp.get("quantity", 1)))
            unit_cost = catalog_match.base_cost_usd if catalog_match else None
            total_cost_item = (qty * unit_cost) if unit_cost else None

            if total_cost_item:
                total_material_cost += total_cost_item

            item = TakeoffItem(
                takeoff_job_id=uuid.UUID(job_id),
                type=comp.get("type", "EQUIPMENT"),
                tag=comp.get("tag"),
                quantity=qty,
                unit=comp.get("unit", "EA"),
                specification=comp.get("specification", ""),
                system=comp.get("system"),
                cfm_or_gpm=Decimal(str(comp["cfm_or_gpm"])) if comp.get("cfm_or_gpm") else None,
                confidence=confidence,
                notes=comp.get("notes"),
                requires_review=requires_review,
                section_index=comp.get("section_index"),
                catalog_item_id=catalog_match.id if catalog_match else None,
                unit_cost_usd=unit_cost,
                total_cost_usd=total_cost_item,
            )
            items_to_insert.append(item)

        session.add_all(items_to_insert)

        low_conf = sum(1 for c in deduped if int(c.get("confidence", 100)) < LOW_CONFIDENCE_THRESHOLD)

        _update_job(session, job_id,
                    status="completed",
                    total_items=len(items_to_insert),
                    low_confidence_count=low_conf,
                    actual_cost_usd=round(total_cost, 4),
                    total_material_cost_usd=total_material_cost,
                    raw_response={"sections": all_raw})

        session.commit()

        # Notify via Redis pub/sub
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL)
        r.publish(
            f"takeoff:{job_id}:status",
            json.dumps({
                "job_id": job_id,
                "status": "completed",
                "total_items": len(items_to_insert),
                "actual_cost_usd": round(total_cost, 4),
            }),
        )
        logger.info("takeoff_complete job_id=%s items=%d cost=$%.4f",
                    job_id, len(items_to_insert), total_cost)

    except Exception as exc:
        logger.exception("run_takeoff_analysis failed: %s", exc)
        session.rollback()
        _update_job(session, job_id, status="failed", error_message=str(exc))
        raise self.retry(exc=exc, countdown=30)
    finally:
        session.close()
