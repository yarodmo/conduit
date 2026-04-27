# syntax=docker/dockerfile:1.6
# ══════════════════════════════════════
# CONDUIT — Backend Dockerfile
# Prompt 0.2 — Hardened Multi-Stage Build
# ══════════════════════════════════════

FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

# Install system dependencies for OpenCV, PyMuPDF, Tesseract
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==1.7.1

COPY pyproject.toml poetry.lock* ./
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi --no-root

# ── Runtime Stage ──
FROM python:3.11-slim-bookworm AS runtime

# Install runtime-only system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    tesseract-ocr \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (Prompt 0.2 Hardening)
RUN addgroup --system app && adduser --system --group app --uid 1000

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application
COPY --chown=app:app ./app ./app
COPY --chown=app:app ./alembic ./alembic
COPY --chown=app:app ./alembic.ini* ./

USER app

# Healthcheck (Prompt 0.2)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
