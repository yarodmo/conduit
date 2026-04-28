##
## Conduit Backend — Developer Makefile
## Bliss Systems LLC | APEX Standard
##

.PHONY: help dev test test-unit test-int lint lint-fix typecheck security migrate seed clean

help:
	@echo "╔══════════════════════════════════════╗"
	@echo "║  CONDUIT BACKEND — Developer CLI     ║"
	@echo "╚══════════════════════════════════════╝"
	@echo ""
	@echo "  make dev          Start dev server (uvicorn reload)"
	@echo "  make test         Run all tests with coverage"
	@echo "  make test-unit    Run unit tests only"
	@echo "  make test-int     Run integration tests only"
	@echo "  make lint         Run ruff linter"
	@echo "  make lint-fix     Auto-fix linting issues"
	@echo "  make typecheck    Run mypy type checking"
	@echo "  make security     Run bandit security scanner"
	@echo "  make migrate      Run Alembic migrations"
	@echo "  make migrate-new  Create new migration: name=<name>"
	@echo "  make seed         Seed database with plans"
	@echo "  make clean        Remove build artifacts"
	@echo ""

# ══════════════════════════════════════
# DEVELOPMENT
# ══════════════════════════════════════

dev:
	@echo "▶ Starting Conduit dev server..."
	poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ══════════════════════════════════════
# TESTING
# ══════════════════════════════════════

test:
	@echo "▶ Running full test suite..."
	poetry run pytest tests/ -v --tb=short

test-unit:
	@echo "▶ Running unit tests..."
	poetry run pytest tests/unit/ -v --tb=short --no-cov

test-int:
	@echo "▶ Running integration tests..."
	poetry run pytest tests/integration/ -v --tb=short

test-watch:
	@echo "▶ Running tests in watch mode..."
	poetry run ptw tests/ -- -v --tb=short --no-cov

# ══════════════════════════════════════
# CODE QUALITY
# ══════════════════════════════════════

lint:
	@echo "▶ Linting with ruff..."
	poetry run ruff check app/ tests/

lint-fix:
	@echo "▶ Auto-fixing lint issues..."
	poetry run ruff check app/ tests/ --fix

typecheck:
	@echo "▶ Type checking with mypy..."
	poetry run mypy app/ --ignore-missing-imports

security:
	@echo "▶ Security scan with bandit..."
	poetry run bandit -r app/ -ll

# ══════════════════════════════════════
# DATABASE
# ══════════════════════════════════════

migrate:
	@echo "▶ Running Alembic migrations..."
	poetry run alembic upgrade head

migrate-new:
	@echo "▶ Creating migration: $(name)"
	poetry run alembic revision --autogenerate -m "$(name)"

migrate-down:
	@echo "▶ Rolling back last migration..."
	poetry run alembic downgrade -1

migrate-history:
	poetry run alembic history --verbose

seed:
	@echo "▶ Seeding subscription plans..."
	poetry run python -m app.scripts.seed_plans

# ══════════════════════════════════════
# CELERY WORKERS
# ══════════════════════════════════════

worker-general:
	@echo "▶ Starting general worker..."
	poetry run celery -A app.tasks.celery_app worker -Q general --loglevel=info

worker-ai:
	@echo "▶ Starting AI worker..."
	poetry run celery -A app.tasks.celery_app worker -Q ai --loglevel=info -c 2

flower:
	@echo "▶ Starting Flower monitor..."
	poetry run celery -A app.tasks.celery_app flower --port=5555

# ══════════════════════════════════════
# KEYS
# ══════════════════════════════════════

generate-keys:
	@echo "▶ Generating RSA keypair..."
	@mkdir -p keys
	@openssl genrsa -out keys/private.pem 2048
	@openssl rsa -in keys/private.pem -pubout -out keys/public.pem
	@echo "✅ Keys saved to keys/ (NOT committed to git)"

# ══════════════════════════════════════
# CLEAN
# ══════════════════════════════════════

clean:
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	@find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; true
	@find . -name "*.pyc" -delete 2>/dev/null; true
	@rm -rf htmlcov/ .coverage 2>/dev/null; true
	@echo "✅ Cleaned"
