# ⚡ CONDUIT — MEP Intelligence. Connected.

> **By Bliss Systems LLC** | The AI-powered operating system for MEP contractors.

---

## 🏗️ What is Conduit?

Conduit is the first unified MEP (Mechanical, Electrical, Plumbing) platform that serves ALL project sizes — from a 1,500 sq ft house to a 300,000 sq ft institutional building — with native AI Vision.

**Core capabilities:**
- 📸 **Photo-First AI Takeoff** — Upload a phone photo of any plan. AI extracts MEP components in minutes.
- 🔧 **Design Simulation Engine (M15)** — Generative MEP design with PE-in-the-loop validation.
- 📱 **Offline-First Field App** — Flutter app for technicians with voice, camera, GPS, and full offline sync.
- 📋 **RFI & Change Order Lifecycle** — Legal-grade traceability from markup to signed change order.
- 🤖 **In-Product AI Assistant** — Ask MEP questions in natural language, get instant answers.

---

## 🛠️ Technology Stack (ADR-000 through ADR-004)

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Backend** | Python 3.11+ / FastAPI / SQLAlchemy 2.0 / Celery | AI/CV ecosystem is Python-native (ADR-000) |
| **Frontend Web** | React 18 / Vite / TypeScript / TailwindCSS | SPA post-login, Konva.js for plan markup (ADR-001) |
| **Mobile** | Flutter 3.x / Dart / Riverpod / Hive | Offline-first for field technicians (ADR-002) |
| **AI Router** | LiteLLM → Claude / Gemini / OpenAI | Multi-provider with cost tracking |
| **Database** | PostgreSQL 15 + pgvector | Embeddings + RAG for material search |
| **Infrastructure** | Docker multi-container + Caddy + CrowdSec | Mythos-Ready security from day 0 |

---

## 📁 Project Structure

```
conduit-app/
├── backend/              ← FastAPI API + Workers + AI Engines
├── frontend-web/         ← React + Vite SPA
├── mobile/               ← Flutter field app
├── infrastructure/       ← Docker, CI/CD, deployment scripts
├── docs/                 ← ADRs, architecture, GTM strategy
├── ops/                  ← Monitoring, alerting, dashboards
├── tests/                ← Cross-cutting security & E2E tests
├── scripts/              ← Dev, deploy, and data utilities
└── config/               ← Environment configs (no secrets)
```

---

## 🚀 Quick Start (Development)

```bash
# 1. Clone
git clone git@github.com:bliss-systems/conduit.git
cd conduit/conduit-app

# 2. Copy environment template
cp config/environments/.env.example .env.local

# 3. Start all services
docker compose -f infrastructure/compose/docker-compose.yml up -d

# 4. Run backend
cd backend && poetry install && uvicorn app.main:app --reload

# 5. Run frontend
cd frontend-web && npm install && npm run dev
```

---

## 📜 Governing Documents

- **Architecture:** `CONDUIT_MASTER_PROMPT_v11.md` (Single Source of Truth)
- **ADRs:** `docs/adr/` (Immutable architectural decisions)
- **Security:** Prompt 0.1 — 16 Mythos-Ready tests required in CI
- **Deploy:** Prompt 0.3 — GitOps blue-green zero-downtime

---

## 🏢 Bliss Systems LLC

- **CEO:** BLISS (Final authority)
- **Domain:** conduit.build
- **Market:** USA — Florida primary, national expansion
- **License:** Proprietary

---

*CONDUIT v11.0 | APEX Standard | Mythos-Ready | Built by Bliss Systems LLC*
