# Plan: Restructure Project into Backend + Frontend

## Context

The OpsComm Pipeline project currently has a flat structure with Python scripts in `scripts/`, a React mockup at root, and shared state/config. The goal is to create a proper `backend/` and `frontend/` folder structure that separates concerns, keeping shared data directories (`state/`, `config/`, `patches/`, `templates/`) at the project root.

This is scaffolding only — we're creating the folder structure, moving/refactoring existing code into proper modules, and setting up the project files (requirements.txt, package.json, etc.). No new features.

---

## Target Structure

```
OpsCommDocsPipeline/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app, CORS, lifespan
│   │   ├── config.py                  # pydantic-settings, loads .env + pipeline.json
│   │   ├── state/
│   │   │   ├── __init__.py
│   │   │   ├── manager.py             # load_tracker(), save_tracker() — from test_sftp.py
│   │   │   └── models.py              # Pydantic models for patch state
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── products.py            # GET /api/products, /api/products/{id}
│   │   │   ├── patches.py             # GET/POST patch endpoints
│   │   │   └── pipeline.py            # POST /api/pipeline/scan
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py        # Coordinates scan → fetch → update state
│   │   │   └── patch_service.py       # find_patch(), status transitions
│   │   ├── pipelines/
│   │   │   ├── __init__.py
│   │   │   ├── binaries/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── fetcher.py         # Download from SFTP
│   │   │   │   └── processor.py       # Post-download verification
│   │   │   └── docs/
│   │   │       ├── __init__.py
│   │   │       └── stub.py            # Placeholder
│   │   └── integrations/
│   │       ├── __init__.py
│   │       ├── sftp/
│   │       │   ├── __init__.py
│   │       │   ├── connector.py       # connect_sftp() — from test_sftp.py
│   │       │   ├── scanner.py         # discover_patches() — from test_sftp.py
│   │       │   └── product_parsers.py # normalize_patch_id(), per-product parsing
│   │       └── jira/
│   │           ├── __init__.py
│   │           ├── client.py          # jira_get(), jira_post() — from test_jira.py
│   │           ├── ticket_builder.py  # text_to_adf(), payload building — from create_jira_ticket.py
│   │           └── attachment.py      # zip + upload — from create_jira_ticket.py
│   ├── requirements.txt               # paramiko, python-dotenv, requests, fastapi, uvicorn, pydantic-settings
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx             # Root layout, dark theme
│   │   │   ├── page.tsx               # Dashboard
│   │   │   └── patches/
│   │   │       ├── page.tsx           # Patch list
│   │   │       └── [product]/
│   │   │           └── [patch]/
│   │   │               └── page.tsx   # Patch detail
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   └── Sidebar.tsx
│   │   │   ├── patches/
│   │   │   │   ├── PatchCard.tsx
│   │   │   │   ├── StatusBadge.tsx
│   │   │   │   └── JiraApprovalModal.tsx
│   │   │   └── shared/
│   │   │       └── DataTable.tsx
│   │   └── lib/
│   │       ├── api.ts                 # Typed fetch wrapper for backend
│   │       ├── types.ts               # TypeScript types matching backend models
│   │       └── constants.ts           # Status colors, theme tokens
│   ├── public/
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── next.config.ts                 # API proxy to backend in dev
│   └── Dockerfile
│
├── state/                             # Stays at root — backend reads/writes
│   └── patches/
│       ├── ACARS_V8_1.json
│       ├── ACARS_V8_0.json
│       └── ACARS_V7_3.json
├── config/
│   └── pipeline.json
├── patches/                           # Downloaded files
├── templates/                         # Doc templates
├── scripts/                           # Keep originals as reference (can remove later)
│   ├── test_sftp.py
│   ├── test_jira.py
│   └── create_jira_ticket.py
├── docker-compose.yml
├── .env
├── .env.example
├── .gitignore
├── CLAUDE.md
├── ARCHITECTURE.md
├── PROGRESS.md
├── FRONTEND_WORKFLOWS.md
└── HANDOFF_JIRA_INTEGRATION.md
```

---

## Decisions

- **Frontend:** use `npx create-next-app` for full scaffold
- **Scripts:** keep `scripts/` as reference after extraction
- **Backend:** extract real working code from scripts (not stubs)

---

## Code Extraction Map

### From `scripts/test_sftp.py` → Backend SFTP + State modules

| Function | Source Lines | Destination |
|----------|-------------|-------------|
| `connect_sftp()` | ~17-30 | `backend/app/integrations/sftp/connector.py` |
| `normalize_patch_id()` | ~32-37 | `backend/app/integrations/sftp/product_parsers.py` |
| `discover_patches_v8_1()` | ~39-95 | `backend/app/integrations/sftp/scanner.py` |
| `discover_patches_v8_0()` | ~97-148 | `backend/app/integrations/sftp/scanner.py` |
| `discover_patches_v7_3()` | ~150-190 | `backend/app/integrations/sftp/scanner.py` |
| `load_tracker()` | ~192-210 | `backend/app/state/manager.py` |
| `save_tracker()` | ~212-220 | `backend/app/state/manager.py` |

### From `scripts/test_jira.py` + `scripts/create_jira_ticket.py` → Backend Jira + Services

| Function | Source | Destination |
|----------|--------|-------------|
| `jira_get()`, `jira_post()` | both scripts | `backend/app/integrations/jira/client.py` |
| `text_to_adf()` | test_jira.py | `backend/app/integrations/jira/ticket_builder.py` |
| Ticket payload construction | create_jira_ticket.py | `backend/app/integrations/jira/ticket_builder.py` |
| Zip + upload attachment | create_jira_ticket.py | `backend/app/integrations/jira/attachment.py` |
| `find_patch()` | create_jira_ticket.py | `backend/app/services/patch_service.py` |
| `check_existing_version()` | create_jira_ticket.py | `backend/app/services/patch_service.py` |

### From `product-control-center-mockup.jsx` → Frontend components

| Mockup Section | Destination |
|----------------|-------------|
| Dashboard view + pie charts | `frontend/src/app/page.tsx` |
| Patch list + status badges | `frontend/src/app/patches/page.tsx` + `components/patches/` |
| JiraApprovalModal component | `frontend/src/components/patches/JiraApprovalModal.tsx` |
| Dark theme tokens (`dk` object) | `frontend/tailwind.config.ts` theme extension |
| Status config + colors | `frontend/src/lib/constants.ts` |
| Hardcoded PRODUCTS data | Replaced by `fetch('/api/...')` calls to backend |

---

## Implementation Steps

### Step 1: Create backend folder structure + requirements
- Create all directories under `backend/app/` with `__init__.py` files
- Create `backend/requirements.txt`: fastapi, uvicorn[standard], pydantic-settings, paramiko, python-dotenv, requests
- Create `backend/Dockerfile`

### Step 2: Extract SFTP code into backend modules
- `connector.py` — paramiko SFTP connection using env vars
- `product_parsers.py` — normalize_patch_id(), per-product version/patch parsing
- `scanner.py` — discover functions refactored to use connector + parsers imports
- `state/manager.py` — load/save tracker with root-relative paths

### Step 3: Extract Jira code into backend modules
- `jira/client.py` — shared HTTP helpers with Basic Auth
- `jira/ticket_builder.py` — ADF conversion + payload construction
- `jira/attachment.py` — zip creation + upload
- `services/patch_service.py` — find_patch(), check_existing_version(), status transitions

### Step 4: Create FastAPI app + API endpoints
- `config.py` — Pydantic Settings loading .env + pipeline.json
- `state/models.py` — Pydantic models matching JSON structure
- `main.py` — FastAPI app with CORS, router includes
- `api/products.py` — product list/detail endpoints
- `api/patches.py` — patch CRUD + approve endpoints
- `api/pipeline.py` — scan trigger + dashboard summary
- `services/orchestrator.py` — scan → discover → update state flow
- `pipelines/` — stubs for binaries fetcher/processor and docs

### Step 5: Scaffold frontend with Next.js
- Run `npx create-next-app@latest frontend` (TypeScript + Tailwind + App Router + src dir)
- Create component directory structure
- Create `lib/api.ts` — typed fetch wrapper
- Create `lib/types.ts` — TypeScript types matching backend
- Create `lib/constants.ts` — status colors + theme tokens from mockup
- Update `next.config.ts` — API proxy rewrite to localhost:8000

### Step 6: Docker Compose + env template
- `docker-compose.yml` with `api` and `web` services
- Backend volume mounts for state/, config/, patches/, templates/
- `.env.example` with all keys (no secrets)

### Step 7: Update project docs + gitignore
- Update `.gitignore` for node_modules/, .next/, frontend/.env.local
- Update `CLAUDE.md` project structure section
- Scripts kept as-is for reference

---

## What stays unchanged
- `state/patches/*.json` — untouched, backend reads from root-relative path
- `config/pipeline.json` — untouched
- `scripts/` — kept as reference
- All `.md` docs — stay at root
- `.env` — stays at root

---

## Verification
- `cd backend && pip install -r requirements.txt && python -m uvicorn app.main:app` → starts on :8000
- `cd frontend && npm install && npm run dev` → starts on :3000
- `curl http://localhost:8000/api/dashboard/summary` → returns JSON
- Frontend dashboard loads and proxies API calls to backend
