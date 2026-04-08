# Plan: Restructure Project into Backend + Frontend

## Context

The OpsComm Pipeline project currently has a flat structure with Python scripts in `scripts/`, a React mockup at root, and shared state/config. The goal is to create a proper `backend/` and `frontend/` folder structure that separates concerns, keeping shared data directories (`state/`, `config/`, `patches/`, `templates/`) at the project root.

This is scaffolding only — we're creating the folder structure, moving/refactoring existing code into proper modules, and setting up the project files (requirements.txt, package.json, etc.). No new features.

## Architecture Decision: Single-Process Deployment

**Frontend:** React + Vite (not Next.js) — simpler, no SSR overhead, builds to static files.
**Deployment:** FastAPI serves both the API and the built frontend from one process on one port.
**Docker:** Single container, single port. No docker-compose needed for two services.

**Why:**
- Single user on localhost — no SSR, no SEO, no multi-user scaling needed
- Same origin = no CORS config, no proxy config
- One command to run: `uvicorn app.main:app`
- The mockup is already pure React — zero rewriting needed

**Dev workflow:** Use Vite dev server (`npm run dev`) with proxy during active UI development for hot reload. Build once with `npm run build` when UI is stable, then just run FastAPI.

---

## Target Structure

```
OpsCommDocsPipeline/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app + serves frontend static files
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
├── frontend/                          # React + Vite (builds to static files)
│   ├── src/
│   │   ├── App.tsx                    # Root component — sidebar + view routing
│   │   ├── main.tsx                   # Entry point
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   └── Header.tsx
│   │   │   ├── patches/
│   │   │   │   ├── PatchTable.tsx
│   │   │   │   ├── StatusBadge.tsx
│   │   │   │   ├── PatchDetailModal.tsx
│   │   │   │   └── JiraApprovalModal.tsx
│   │   │   └── shared/
│   │   │       ├── SummaryCard.tsx
│   │   │       ├── Th.tsx
│   │   │       └── Td.tsx
│   │   ├── views/
│   │   │   ├── Dashboard.tsx          # Dashboard view
│   │   │   └── Pipeline.tsx           # Pipeline view (actionable + history)
│   │   └── lib/
│   │       ├── api.ts                 # Typed fetch wrapper (/api/*)
│   │       ├── types.ts               # TypeScript types matching backend models
│   │       └── constants.ts           # Theme tokens, status config, field options
│   ├── index.html
│   ├── public/
│   ├── package.json
│   ├── vite.config.ts                 # Dev proxy: /api → localhost:8000
│   ├── tailwind.config.ts
│   └── tsconfig.json
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
├── Dockerfile                         # Single container: Python + built frontend
├── .env
├── .env.example
├── .gitignore
├── CLAUDE.md
├── ARCHITECTURE.md
├── PROGRESS.md
├── FRONTEND_WORKFLOWS.md
└── HANDOFF.md
```

---

## Decisions

- **Frontend:** use `npm create vite@latest frontend -- --template react-ts` for scaffold
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
| Dashboard view + pie charts | `frontend/src/views/Dashboard.tsx` |
| Patch list + status badges | `frontend/src/views/Pipeline.tsx` + `components/patches/` |
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
- `main.py` — FastAPI app, router includes, serves frontend static files via `StaticFiles`
- `api/products.py` — product list/detail endpoints
- `api/patches.py` — patch CRUD + approve endpoints
- `api/pipeline.py` — scan trigger + dashboard summary
- `services/orchestrator.py` — scan → discover → update state flow
- `pipelines/` — stubs for binaries fetcher/processor and docs
- No CORS config needed — frontend served from same origin

### Step 5: Scaffold frontend with React + Vite
- Run `npm create vite@latest frontend -- --template react-ts`
- Install Tailwind, lucide-react, recharts, @tanstack/react-query, sonner
- Create component directory structure
- Create `lib/api.ts` — typed fetch wrapper (`/api/*` calls)
- Create `lib/types.ts` — TypeScript types matching backend models
- Create `lib/constants.ts` — theme tokens + status config from mockup
- Update `vite.config.ts` — dev proxy: `/api` → `http://localhost:8000`

### Step 6: Docker + env template
- Single `Dockerfile` at root: multi-stage build (Node builds frontend, Python runs everything)
- `.env.example` with all keys (no secrets)
- Run: `docker build -t opscomm-pipeline . && docker run -p 8000:8000 opscomm-pipeline`

### Step 7: Update project docs + gitignore
- Update `.gitignore` for node_modules/, frontend/dist/
- Update `CLAUDE.md` project structure section
- Scripts kept as-is for reference

---

## Logging

All backend operations must produce clear, structured logs so you can see exactly what's happening and trace failures.

### Logging Setup (`backend/app/logging_config.py`)
- Use Python's `logging` module with structured format: `[timestamp] [level] [module] message`
- Log to stdout (visible in terminal) AND to `logs/pipeline.log` (rotated, persistent)
- Log levels: DEBUG for dev, INFO for production
- Each module gets its own named logger: `sftp.connector`, `sftp.scanner`, `jira.client`, etc.

### What gets logged

**SFTP operations** (`integrations/sftp/`):
- `INFO` — SFTP connection opened/closed, host + username
- `INFO` — Scan started for product {product_id}
- `INFO` — Discovered {N} new patches for {product_id}: [{patch_ids}]
- `INFO` — Downloading patch {patch_id} from {sftp_path} → {local_path}
- `INFO` — Download complete: {file_count} files, {total_size}
- `WARNING` — Patch {patch_id} already exists in tracker, skipping
- `ERROR` — SFTP connection failed: {error}
- `ERROR` — Download failed for {patch_id}: {error}
- `DEBUG` — Listing directory {path}: [{folders}]
- `DEBUG` — Normalized patch ID: {raw} → {normalized}

**Jira operations** (`integrations/jira/`):
- `INFO` — Creating Jira ticket for {patch_id} ({pipeline_type})
- `INFO` — Jira ticket created: {ticket_key} — {ticket_url}
- `INFO` — Uploading attachment {filename} to {ticket_key}
- `INFO` — Attachment uploaded successfully
- `INFO` — JQL search: {query} → {result_count} results
- `WARNING` — Jira returned unexpected status {code}: {body}
- `ERROR` — Jira ticket creation failed: {status_code} {error_body}
- `ERROR` — Attachment upload failed: {error}
- `DEBUG` — Jira request: {method} {url}
- `DEBUG` — Jira response: {status_code} {body_preview}

**State operations** (`state/manager.py`):
- `INFO` — Loaded tracker for {product_id}: {patch_count} patches
- `INFO` — Saved tracker for {product_id} (atomic write)
- `ERROR` — Failed to load tracker {filepath}: {error}
- `ERROR` — Failed to save tracker {filepath}: {error}

**API endpoints** (`api/`):
- `INFO` — Scan triggered for {products}
- `INFO` — Approve {pipeline_type} for {product_id}/{patch_id}
- `INFO` — Status transition: {patch_id} {old_status} → {new_status}
- `ERROR` — Approve failed for {patch_id}: {error}

**Pipeline orchestrator** (`services/orchestrator.py`):
- `INFO` — Pipeline run started: {product_ids}
- `INFO` — Pipeline run complete: {new_count} new, {error_count} errors
- `ERROR` — Pipeline failed for {product_id}: {error}

### Log file location
```
logs/
├── pipeline.log        # Main log (rotated at 5MB, keep 5 backups)
└── pipeline.log.1      # Previous rotation
```

Add `logs/` to `.gitignore`.

---

## Error Handling

### Backend error strategy

**API layer** — Every endpoint returns structured error responses:
```json
{
  "error": "Jira ticket creation failed",
  "detail": "401 Unauthorized — API token may have expired",
  "patch_id": "8.1.12.0",
  "pipeline": "binaries",
  "step": "jira_create",
  "timestamp": "2026-04-08T10:00:00Z"
}
```
- HTTP 200 for success, 400 for bad requests, 500 for internal errors
- Always include `detail` with a human-readable explanation
- Always include `step` so you know exactly where it failed

**SFTP errors** — Connection timeout, auth failure, file not found:
- Catch `paramiko.SSHException`, `paramiko.AuthenticationException`, `IOError`
- Log full error + retry hint
- Return to caller with clear error message, don't crash the server

**Jira errors** — Auth expired, field validation, rate limits:
- Catch HTTP 401 (token expired), 400 (bad payload), 429 (rate limited)
- On 401: log "API token may have expired — check .env JIRA_API_TOKEN_NO_SCOPES"
- On 400: log the full Jira error response (it tells you which field failed)
- On 429: log "Rate limited by Jira — wait and retry"
- Status stays at `approved` (not `published`) so user can retry

**State errors** — File not found, JSON parse error, write failure:
- If tracker file missing: create empty tracker, log warning
- If JSON corrupt: log error with file path, don't overwrite (preserve for debugging)
- Atomic writes (write to .tmp → rename) prevent half-written state

**Status transition errors** — Wrong status for operation:
- Approve on already-published patch: 400 "Patch already published"
- Approve on discovered (not yet downloaded): 400 "Patch not ready for approval — status is {status}"
- Log the attempted invalid transition

### Error propagation
```
Integration layer (sftp/jira) → raises specific exceptions
Service layer (orchestrator)  → catches, logs, wraps in result object
API layer (endpoints)         → returns structured JSON error to frontend
Frontend                      → shows toast with error message
```

Never swallow errors silently. Every `except` block must log.

---

## Testing

### Backend tests (`backend/tests/`)

**Unit tests** (no external dependencies):
```
tests/
├── test_product_parsers.py    # normalize_patch_id(), version parsing
├── test_state_manager.py      # load/save tracker with temp files
├── test_patch_service.py      # find_patch(), status transitions, validation
├── test_ticket_builder.py     # text_to_adf(), payload construction
└── test_models.py             # Pydantic model validation
```

Key test cases:
- `normalize_patch_id("v8.1.0.0")` → `"8.1.0.0"`
- `normalize_patch_id("8_0_28_1")` → `"8.0.28.1"`
- `normalize_patch_id("7_3_27_7")` → `"7.3.27.7"`
- Load tracker from valid JSON → correct structure
- Load tracker from missing file → empty tracker created
- Save tracker → atomic write (tmp + rename)
- Status transition `pending_approval → approved` → OK
- Status transition `discovered → approved` → rejected
- Status transition `published → approved` → rejected
- `text_to_adf("hello")` → valid ADF JSON
- Jira payload for new folder → `"New CAE Portal Release"`
- Jira payload for existing folder → `"Existing CAE Portal Release"`

**Integration tests** (hit real SFTP/Jira — run manually):
```
tests/
├── test_sftp_connection.py    # Connect + list root directory
├── test_jira_connection.py    # Auth + get myself
└── test_jira_dry_run.py       # Build payload, validate (don't create)
```

These are essentially your existing `test_sftp.py` and `test_jira.py` migrated into pytest format.

**API tests** (FastAPI TestClient, no external deps):
```
tests/
├── test_api_products.py       # GET /api/products returns correct shape
├── test_api_patches.py        # GET /api/patches, approve flow
├── test_api_pipeline.py       # POST /api/pipeline/scan (mocked SFTP)
└── test_api_dashboard.py      # GET /api/dashboard/summary counts
```

Use FastAPI's `TestClient` with mocked integrations (mock SFTP, mock Jira).

### Test runner
- `pytest` with `pytest-asyncio` for async endpoints
- Add to `backend/requirements.txt`: pytest, pytest-asyncio, httpx (for TestClient)
- Run: `cd backend && pytest -v`

---

## What stays unchanged
- `state/patches/*.json` — untouched, backend reads from root-relative path
- `config/pipeline.json` — untouched
- `scripts/` — kept as reference
- All `.md` docs — stay at root
- `.env` — stays at root

---

## Verification

**Dev mode (two terminals):**
- `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload` → API on :8000
- `cd frontend && npm install && npm run dev` → Vite dev server on :5173, proxies /api to :8000
- Open `http://localhost:5173` → dashboard loads with hot reload

**Production mode (one process):**
- `cd frontend && npm run build` → builds to `frontend/dist/`
- `cd backend && uvicorn app.main:app` → serves API + frontend on :8000
- Open `http://localhost:8000` → dashboard + API on same port, no proxy
- `curl http://localhost:8000/api/dashboard/summary` → returns JSON

**Docker:**
- `docker build -t opscomm-pipeline .`
- `docker run -p 8000:8000 --env-file .env opscomm-pipeline`
- Open `http://localhost:8000` → everything in one container
