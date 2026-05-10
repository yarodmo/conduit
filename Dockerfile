# Conduit Backend — Dockerfile
# Multi-stage: builder + slim runtime image
# Bliss Systems LLC — APEX Standard

# ── Stage 1: Builder ──────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==1.8.3

COPY backend/pyproject.toml backend/poetry.lock* ./

# Install deps directly into a venv — avoids poetry-plugin-export bugs
RUN poetry config virtualenvs.in-project true \
    && poetry install --without dev --no-root --no-interaction --no-ansi


# ── Stage 2: Runtime ──────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy venv from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY backend/ .

# Non-root user for security
RUN useradd -m -u 1000 conduit && chown -R conduit:conduit /app
USER conduit

# Port 3007 — within CSF TCP_IN whitelist (3000:3200) on shared VPS.
# Pattern aligned with hitdash:3001/3005. Container internal AND host
# binding must both be in whitelisted range, otherwise CSF RSTs traffic
# even on Docker bridge IPs.
EXPOSE 3007

# Production: uvicorn with multiple workers
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3007", \
     "--workers", "2", "--loop", "uvloop", "--http", "httptools", \
     "--no-access-log"]
