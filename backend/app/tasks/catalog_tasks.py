"""
Conduit Backend — Catalog Tasks (M12)
Async embedding generation + large CSV import via Celery worker-general.

Bliss Systems LLC — APEX Standard
"""

import json
import structlog

from app.tasks.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(name="app.tasks.catalog_tasks.generate_item_embedding",
                 bind=True, max_retries=2, default_retry_delay=60)
def generate_item_embedding(self, item_id: str, specification: str, tag_prefix: str) -> None:
    """Generate and store pgvector embedding for a catalog item."""
    try:
        from app.core.config import settings
        if settings.ENVIRONMENT in ("test", "development"):
            return

        import litellm
        text_input = f"{tag_prefix} {specification}".strip()
        resp = litellm.embedding(model="text-embedding-3-small", input=[text_input])
        embedding = resp.data[0]["embedding"]

        import psycopg2
        conn = psycopg2.connect(settings.DATABASE_URL.replace("+asyncpg", ""))
        cur = conn.cursor()
        cur.execute(
            "UPDATE material_catalog SET embedding = %s WHERE id = %s",
            (json.dumps(embedding), item_id),
        )
        conn.commit()
        conn.close()
        logger.info("catalog_embedding_generated", item_id=item_id)

    except Exception as exc:
        logger.error("catalog_embedding_failed", item_id=item_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(name="app.tasks.catalog_tasks.process_csv_import",
                 bind=True, max_retries=1, default_retry_delay=30)
def process_csv_import(self, job_id: str, csv_content: str) -> None:
    """Process large CSV imports (>500 rows) in worker context."""
    try:
        import asyncio
        import csv
        import io
        from decimal import Decimal
        from datetime import datetime, timezone

        import psycopg2
        from app.core.config import settings

        conn = psycopg2.connect(settings.DATABASE_URL.replace("+asyncpg", ""))
        cur = conn.cursor()

        cur.execute("SELECT org_id FROM catalog_import_jobs WHERE id = %s", (job_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return
        org_id = str(row[0])

        cur.execute("UPDATE catalog_import_jobs SET status='processing' WHERE id=%s", (job_id,))
        conn.commit()

        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        created = updated = failed = 0
        errors = []

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
                base_cost = float(cost_raw) if cost_raw else None

                cur.execute(
                    """SELECT id FROM material_catalog
                       WHERE org_id=%s AND item_type=%s AND specification=%s LIMIT 1""",
                    (org_id, item_type, description),
                )
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        """UPDATE material_catalog SET base_cost_usd=COALESCE(%s, base_cost_usd),
                           supplier_name=COALESCE(%s, supplier_name),
                           supplier_sku=COALESCE(%s, supplier_sku)
                           WHERE id=%s""",
                        (base_cost, supplier_name, supplier_sku, str(existing[0])),
                    )
                    updated += 1
                else:
                    cur.execute(
                        """INSERT INTO material_catalog
                           (id, org_id, item_type, specification, description,
                            tag_prefix, category, unit, base_cost_usd,
                            supplier_name, supplier_sku, is_custom, is_active,
                            created_at, updated_at)
                           VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s,
                                   %s, %s, %s, %s, true, true, now(), now())""",
                        (org_id, item_type, description, description,
                         tag_prefix, category, unit, base_cost,
                         supplier_name, supplier_sku),
                    )
                    created += 1
            except Exception as e:
                failed += 1
                errors.append({"row": i, "error": str(e)})

        conn.commit()
        now = datetime.now(tz=timezone.utc)
        cur.execute(
            """UPDATE catalog_import_jobs
               SET status='completed', rows_created=%s, rows_updated=%s,
                   rows_failed=%s, errors=%s, completed_at=%s
               WHERE id=%s""",
            (created, updated, failed,
             json.dumps(errors) if errors else None, now, job_id),
        )
        conn.commit()
        conn.close()
        logger.info("csv_import_completed", job_id=job_id,
                    created=created, updated=updated, failed=failed)

    except Exception as exc:
        logger.error("csv_import_failed", job_id=job_id, error=str(exc))
        raise self.retry(exc=exc)
