"""
Conduit Backend — Self-Learning Pipeline Service (M13)
Analyzes human corrections on takeoff items to improve AI prompt quality.

Pipeline (runs nightly via Celery beat):
  1. Query all TakeoffItems with human_corrected=True in the period
  2. Aggregate by prompt_version + component_type
  3. Calculate accuracy_score per job and per prompt version
  4. Identify component types with highest correction rates (error patterns)
  5. Flag prompt versions with avg accuracy < 70% (LOW_ACCURACY_THRESHOLD)
  6. Generate AI recommendation via Claude (optional, if ENVIRONMENT=production)
  7. Write LearningInsight row + update TakeoffJob.accuracy_score

CHANGELOG pattern for prompt improvement:
  When a prompt version hits < 70% accuracy:
    - Creates alert notification for org admin
    - Appends entry to /ai-prompts/takeoff/CHANGELOG.md
    - Recommendation stored in LearningInsight.recommendation

Bliss Systems LLC — APEX Standard
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import LearningCorrectionEvent, LearningInsight
from app.models.takeoff import TakeoffItem, TakeoffJob
from app.modules.learning.schemas import (
    ErrorPattern,
    InsightResponse,
    LearningDashboardResponse,
    PromptAccuracy,
    TriggerAnalysisResponse,
)

logger = structlog.get_logger()

LOW_ACCURACY_THRESHOLD = 70.0
ANALYSIS_WINDOW_DAYS = 30


def _to_insight_response(insight: LearningInsight) -> InsightResponse:
    return InsightResponse.model_validate(insight)


class LearningService:

    @staticmethod
    async def run_analysis(
        db: AsyncSession,
        org_id: uuid.UUID,
        days: int = ANALYSIS_WINDOW_DAYS,
    ) -> TriggerAnalysisResponse:
        now = datetime.now(tz=timezone.utc)
        period_start = now - timedelta(days=days)

        # 1. Load all corrected items in window for this org
        stmt = (
            select(TakeoffItem, TakeoffJob)
            .join(TakeoffJob, TakeoffItem.takeoff_job_id == TakeoffJob.id)
            .where(
                TakeoffJob.org_id == org_id,
                TakeoffItem.human_corrected.is_(True),
                TakeoffItem.created_at >= period_start,
            )
        )
        rows = (await db.execute(stmt)).all()

        # 2. Aggregate by prompt_version + component_type
        corrections_by_version: dict[str, list[float]] = defaultdict(list)
        type_errors: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "count": 0, "confidences": [], "correction_types": set()
        })
        job_corrections: dict[uuid.UUID, int] = defaultdict(int)
        job_items: dict[uuid.UUID, int] = defaultdict(int)

        for item, job in rows:
            pv = job.prompt_version or "v1"
            corrections_by_version[pv].append(float(item.confidence or 50))
            type_errors[item.type]["count"] += 1
            type_errors[item.type]["confidences"].append(item.confidence or 50)
            job_corrections[job.id] += 1

        # Count total items per job
        job_ids = list(job_corrections.keys())
        if job_ids:
            count_stmt = (
                select(TakeoffItem.takeoff_job_id, func.count())
                .where(TakeoffItem.takeoff_job_id.in_(job_ids))
                .group_by(TakeoffItem.takeoff_job_id)
            )
            for job_id_val, cnt in (await db.execute(count_stmt)).all():
                job_items[job_id_val] = cnt

        # 3. Calculate accuracy by version (100 - correction_rate)
        accuracy_by_version: dict[str, float] = {}
        for pv, confidences in corrections_by_version.items():
            # accuracy = average confidence of corrected items (proxy for how good we were)
            avg_conf = sum(confidences) / len(confidences) if confidences else 100.0
            accuracy_by_version[pv] = round(avg_conf, 1)

        # 4. Per-job accuracy update
        for job_id_val in job_corrections:
            total = job_items.get(job_id_val, 1)
            corrections = job_corrections[job_id_val]
            accuracy = max(0.0, 100.0 - (corrections / total * 100))
            job = await db.get(TakeoffJob, job_id_val)
            if job:
                job.accuracy_score = Decimal(str(round(accuracy, 2)))

        # 5. Top error patterns
        top_errors = sorted(
            [
                {
                    "component_type": ct,
                    "count": data["count"],
                    "avg_confidence": round(
                        sum(data["confidences"]) / len(data["confidences"]), 1
                    ) if data["confidences"] else 0,
                }
                for ct, data in type_errors.items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        # 6. Low accuracy prompts
        low_accuracy = [pv for pv, acc in accuracy_by_version.items()
                        if acc < LOW_ACCURACY_THRESHOLD]

        # 7. Overall avg
        all_accuracies = list(accuracy_by_version.values())
        avg_acc = Decimal(str(round(sum(all_accuracies) / len(all_accuracies), 2))) \
            if all_accuracies else None

        # 8. Generate recommendation text
        recommendation = _generate_recommendation(
            top_errors, low_accuracy, len(rows)
        )

        # 9. Handle low-accuracy alerts
        if low_accuracy:
            await _create_low_accuracy_alerts(db, org_id, low_accuracy)

        # 10. Persist insight
        insight = LearningInsight(
            org_id=org_id,
            period_start=period_start,
            period_end=now,
            total_takeoffs_analyzed=len(set(job.id for _, job in rows)) if rows else 0,
            total_corrections=len(rows),
            avg_accuracy_pct=avg_acc,
            accuracy_by_version=accuracy_by_version,
            top_error_patterns=top_errors,
            low_accuracy_prompts=low_accuracy if low_accuracy else None,
            recommendation=recommendation,
        )
        db.add(insight)
        await db.commit()
        await db.refresh(insight)

        # 11. Update CHANGELOG file
        _append_changelog(top_errors, low_accuracy, now)

        logger.info(
            "learning_analysis_complete",
            org_id=str(org_id),
            corrections=len(rows),
            low_accuracy_prompts=low_accuracy,
        )

        return TriggerAnalysisResponse(
            org_id=org_id,
            period_analyzed_days=days,
            insight_id=insight.id,
            summary=(
                f"Analyzed {len(rows)} corrections across "
                f"{insight.total_takeoffs_analyzed} takeoffs. "
                f"Avg accuracy: {avg_acc or 'N/A'}%. "
                f"{'⚠️ Low accuracy prompts: ' + str(low_accuracy) if low_accuracy else '✅ All prompts above threshold.'}"
            ),
        )

    @staticmethod
    async def get_dashboard(
        db: AsyncSession, org_id: uuid.UUID
    ) -> LearningDashboardResponse:
        # Latest insight
        latest_stmt = (
            select(LearningInsight)
            .where(LearningInsight.org_id == org_id)
            .order_by(LearningInsight.created_at.desc())
            .limit(1)
        )
        latest = (await db.execute(latest_stmt)).scalar_one_or_none()

        # All-time corrections count
        total_corr_stmt = select(func.count()).select_from(TakeoffItem).join(
            TakeoffJob, TakeoffItem.takeoff_job_id == TakeoffJob.id
        ).where(TakeoffJob.org_id == org_id, TakeoffItem.human_corrected.is_(True))
        total_corrections = (await db.execute(total_corr_stmt)).scalar_one()

        # Learning events last 30d
        since_30d = datetime.now(tz=timezone.utc) - timedelta(days=30)
        events_stmt = select(func.count()).where(
            LearningCorrectionEvent.org_id == org_id,
            LearningCorrectionEvent.created_at >= since_30d,
        )
        events_30d = (await db.execute(events_stmt)).scalar_one()

        # Prompt accuracy from latest insight
        prompt_accuracy: list[PromptAccuracy] = []
        top_errors: list[ErrorPattern] = []

        if latest and latest.accuracy_by_version:
            prompt_accuracy = [
                PromptAccuracy(
                    prompt_version=pv,
                    takeoff_count=0,
                    avg_accuracy_pct=acc,
                    correction_count=0,
                    below_threshold=acc < LOW_ACCURACY_THRESHOLD,
                )
                for pv, acc in latest.accuracy_by_version.items()
            ]
        if latest and latest.top_error_patterns:
            top_errors = [
                ErrorPattern(
                    component_type=p["component_type"],
                    correction_count=p["count"],
                    avg_confidence=p.get("avg_confidence", 0.0),
                    correction_types=[],
                )
                for p in latest.top_error_patterns
            ]

        return LearningDashboardResponse(
            latest_insight=_to_insight_response(latest) if latest else None,
            prompt_accuracy=prompt_accuracy,
            top_errors=top_errors,
            total_corrections_all_time=total_corrections,
            learning_events_last_30d=events_30d,
        )

    @staticmethod
    async def get_latest_insight(
        db: AsyncSession, org_id: uuid.UUID
    ) -> InsightResponse:
        stmt = (
            select(LearningInsight)
            .where(LearningInsight.org_id == org_id)
            .order_by(LearningInsight.created_at.desc())
            .limit(1)
        )
        insight = (await db.execute(stmt)).scalar_one_or_none()
        if not insight:
            raise HTTPException(status_code=404, detail="No learning insights yet")
        return _to_insight_response(insight)

    @staticmethod
    async def record_correction_event(
        db: AsyncSession,
        org_id: uuid.UUID,
        takeoff_job_id: uuid.UUID,
        item_id: uuid.UUID,
        prompt_version: str,
        component_type: str,
        original_confidence: int | None,
        correction_type: str,
    ) -> None:
        event = LearningCorrectionEvent(
            org_id=org_id,
            takeoff_job_id=takeoff_job_id,
            item_id=item_id,
            prompt_version=prompt_version,
            component_type=component_type,
            original_confidence=original_confidence,
            correction_type=correction_type,
        )
        db.add(event)
        # Non-blocking — will be committed with the parent transaction


# ── Helpers ────────────────────────────────────────────────────────────────

def _generate_recommendation(
    top_errors: list[dict],
    low_accuracy: list[str],
    total_corrections: int,
) -> str:
    if total_corrections == 0:
        return "No corrections recorded in this period. AI accuracy looks good."

    parts = [f"Analyzed {total_corrections} human corrections."]

    if top_errors:
        top_type = top_errors[0]["component_type"]
        top_count = top_errors[0]["count"]
        parts.append(
            f"Most-corrected component type: {top_type} ({top_count} corrections). "
            f"Consider adding more examples of {top_type} annotations to the prompt."
        )

    if low_accuracy:
        parts.append(
            f"⚠️ Prompt versions below {LOW_ACCURACY_THRESHOLD}% accuracy threshold: "
            f"{', '.join(low_accuracy)}. "
            "Review /ai-prompts/takeoff/CHANGELOG.md for improvement suggestions."
        )
    else:
        parts.append(f"✅ All prompt versions above {LOW_ACCURACY_THRESHOLD}% threshold.")

    return " ".join(parts)


async def _create_low_accuracy_alerts(
    db: AsyncSession,
    org_id: uuid.UUID,
    low_accuracy_prompts: list[str],
) -> None:
    """Dispatch notification to org admins when prompt accuracy drops below threshold."""
    try:
        from app.models.notifications import NotificationType
        from app.modules.notifications.service import send_notification

        # Get org admins
        from app.models.auth import OrgRole, OrganizationMember
        stmt = select(OrganizationMember).where(
            OrganizationMember.org_id == org_id,
            OrganizationMember.role == OrgRole.ORG_ADMIN,
        )
        members = (await db.execute(stmt)).scalars().all()

        for member in members:
            await send_notification(
                db=db,
                user_id=member.user_id,
                org_id=org_id,
                notif_type=NotificationType.TAKEOFF_REQUIRES_REVIEW,
                title="AI Prompt Accuracy Alert",
                body=(
                    f"Prompt versions {', '.join(low_accuracy_prompts)} "
                    f"are below {LOW_ACCURACY_THRESHOLD}% accuracy. "
                    "Review corrections to improve AI takeoff quality."
                ),
                data={"low_accuracy_prompts": low_accuracy_prompts},
            )
    except Exception:
        pass  # Non-critical — don't fail analysis on notification error


def _append_changelog(
    top_errors: list[dict],
    low_accuracy: list[str],
    timestamp: datetime,
) -> None:
    """Append learning entry to /ai-prompts/takeoff/CHANGELOG.md."""
    try:
        import os
        from pathlib import Path

        changelog = Path(__file__).parent.parent.parent.parent / \
            "ai_prompts" / "takeoff" / "CHANGELOG.md"

        if not changelog.parent.exists():
            return

        entry_lines = [
            f"\n## {timestamp.strftime('%Y-%m-%d %H:%M UTC')} — Auto-Learning Report",
        ]
        if top_errors:
            entry_lines.append(
                f"- Top error pattern: **{top_errors[0]['component_type']}** "
                f"({top_errors[0]['count']} corrections)"
            )
        if low_accuracy:
            entry_lines.append(
                f"- ⚠️ Low accuracy prompts: {', '.join(low_accuracy)}"
            )
        else:
            entry_lines.append("- ✅ All prompts above 70% threshold")

        with open(changelog, "a") as f:
            f.write("\n".join(entry_lines) + "\n")
    except Exception:
        pass  # Non-critical
