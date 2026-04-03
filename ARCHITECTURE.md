# OpsComm Pipeline — Architecture & Implementation Plan

## Context

The OpsComm Pipeline is the **first module** of a larger Product Control Center — a modular platform where independent pipelines can be plugged in to automate operations workflows. The first pipeline handles SFTP ingestion of software releases (binaries + documentation) for the OpsComm / ACARS product family.

### SFTP Structure (validated 2026-04-03 from live server)

```
SFTP Root/
├── ACARS_V8_1/                        ← product (hierarchical, 2 levels to patch)
│   ├── ACARS_V8_1_0/                  ← version folder (8.1.0)
│   │   ├── v8.1.0.0/                  ← patch ("v" prefix, dots — early naming)
│   │   ├── v8.1.0.1/
│   │   ├── v8.1.0.2/
│   │   └── v8.1.0.3/
│   ├── ACARS_V8_1_1/
│   ├── ACARS_V8_1_3/
│   ├── ACARS_V8_1_4/
│   ├── ACARS_V8_1_5/
│   ├── ACARS_V8_1_7/                  ← note: V8.1.2 and V8.1.6 don't exist
│   ├── ACARS_V8_1_8/
│   ├── ACARS_V8_1_9/
│   ├── ACARS_V8_1_10/                 ← from here: no "v" prefix (8.1.10.0)
│   ├── ACARS_V8_1_11/
│   └── ACARS_V8_1_12/
│
├── ACARS_V8_0/                        ← product (hierarchical, 2 levels to patch)
│   ├── 8_0_4/                         ← version folders: 8_0_{minor} (NOT ACARS_V8_0_{minor})
│   ├── ...
│   ├── 8_0_28/                        ← TRACK FROM HERE
│   │   ├── 8_0_28_0/
│   │   └── 8_0_28_1/
│   ├── 8_0_29/
│   └── 8_0_30/
│
├── ACARS_V7_3/                        ← product (FLAT — 1 level to patch)
│   ├── 7_3_27_0/                      ← TRACK FROM HERE. Version 7.3.27 parsed from name
│   ├── 7_3_27_1/
│   ├── 7_3_27_5/
│   ├── 7_3_27_7/
│   └── 7_3_27_8/
│
├── ACARS_V7_2/                        ← not tracked
├── ACARS_V7_1/                        ← not tracked
└── AIRPORT_SCRIPTS/                   ← not tracked
```

**Key observations (validated):**
- **V8.1**: version folders `ACARS_V8_1_{minor}`, patches use `v` prefix early (`v8.1.0.0`) and drop it later (`8.1.10.0`). Versions 8.1.2 and 8.1.6 don't exist on SFTP. Track ALL.
- **V8.0**: version folders are `8_0_{minor}` (not `ACARS_V8_0_{minor}`). Ranges from 8_0_4 to 8_0_30. Track from 8_0_28.
- **V7.3**: FLAT on SFTP — patches sit directly under product. Version parsed from folder name (`7_3_27_7` → version 7.3.27, patch 7.3.27.7). Track from 7_3_27_0.
- All patch IDs are **normalized to dotted format** in the tracker (e.g., `7_3_27_7` → `7.3.27.7`, `v8.1.9.1` → `8.1.9.1`).
- All products stored **hierarchically in tracker** as `version/patch`, even V7.3.

**MVP scope:** SFTP discovery → download patch folder → manual approval → mark published.
Docs pipeline is designed but not active (no docs in tracked range).

---

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | **Python + FastAPI** | Best for SFTP/docx work, async, auto OpenAPI docs |
| Frontend | **Next.js (TypeScript) + Tailwind** | Fast iteration, wrappable in Tauri later |
| State | **JSON files on disk** | Simple, debuggable, no DB overhead for MVP |
| Containerization | **Docker Compose** | Backend + frontend, runs on Mac now, deployable later |
| Triggering | **Manual** (API/UI button) | No auto-polling. Future: triggered by email |

**Future additions** (when needed): PostgreSQL, WebSockets, Alembic migrations, event bus.

---

## Project Structure

```
OpsCommDocsPipeline/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app, lifespan, CORS
│   │   ├── config.py                  # pydantic-settings (env vars)
│   │   ├── state/
│   │   │   ├── manager.py             # JSON state read/write (atomic)
│   │   │   └── models.py              # Pydantic models for state
│   │   ├── api/
│   │   │   ├── products.py            # Product endpoints
│   │   │   ├── patches.py             # Patch list/detail/approve/publish
│   │   │   └── pipeline.py            # Scan + fetch triggers
│   │   ├── services/
│   │   │   ├── orchestrator.py        # Coordinates scan → fetch → update state
│   │   │   └── patch_service.py       # Status transitions + validation
│   │   ├── pipelines/
│   │   │   ├── base.py                # PipelineBase ABC
│   │   │   ├── binaries/
│   │   │   │   ├── fetcher.py         # Download non-DOC/ contents from SFTP
│   │   │   │   └── processor.py       # Post-download verification
│   │   │   └── docs/
│   │   │       └── stub.py            # Placeholder (returns "skipped")
│   │   └── integrations/
│   │       ├── sftp/
│   │       │   ├── connector.py       # SFTPConnector (paramiko)
│   │       │   ├── scanner.py         # Discovers new patches on SFTP
│   │       │   └── product_parsers.py # Parse folder names per product
│   │       └── jira/
│   │           ├── client.py          # JiraClient (requests + Basic Auth)
│   │           ├── ticket_builder.py  # Build payloads from patch state
│   │           └── attachment.py      # Zip + upload binaries
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/                       # Next.js App Router
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx               # Dashboard
│   │   │   └── patches/               # Patch list + detail
│   │   ├── components/
│   │   │   ├── layout/                # Sidebar, Header
│   │   │   ├── patches/               # PatchCard, StatusBadge
│   │   │   └── shared/                # DataTable, filters
│   │   └── lib/
│   │       ├── api.ts                 # Typed fetch wrapper
│   │       └── types.ts
│   ├── Dockerfile
│   ├── package.json
│   └── tailwind.config.ts
├── state/                             # Runtime state (JSON files)
│   ├── products.json
│   └── patches/
│       ├── ACARS_V8_1.json
│       ├── ACARS_V8_0.json
│       └── ACARS_V7_3.json
├── config/                            # Product definitions + legacy state
│   └── pipeline.json             # Products, lifecycle, Jira fields, portal settings
├── patches/                           # Downloaded files (bind-mounted)
├── templates/                         # Docx templates (future)
├── docker-compose.yml
└── .env.example
```

---

## State Tracking (JSON Files)

No database for now. State lives in JSON files under `state/`, one file per product line.

### Pipeline Config: `config/pipeline.json`

Single config file containing product definitions, patch lifecycle, Jira field mappings, and portal settings. Products are accessed at `pipeline.products`:

```json
{
  "pipeline": {
    "name": "OpsComm Docs & Binaries Pipeline",
    "products": {
      "ACARS_V8_1": {
        "display_name": "ACARS V8.1",
        "sftp_path": "/ACARS_V8_1",
        "structure_type": "hierarchical",
        "track_from": null
      },
      "ACARS_V8_0": { "...": "..." },
      "ACARS_V7_3": { "...": "..." }
    },
    "patch_lifecycle": { "statuses": ["discovered", "downloaded", "pending_approval", "approved", "published"] },
    "jira": { "...": "field mappings, templates, attachment config" },
    "community_portal": { "...": "portal settings" }
  }
}
```

### Patch State: `state/patches/{PRODUCT_ID}.json`

One file per product. All products stored hierarchically: **product → version → patch**.
Patch IDs are normalized to dotted format regardless of SFTP folder naming.

```json
{
  "product_id": "ACARS_V7_3",
  "last_scanned_at": "2026-04-03T17:04:36Z",
  "versions": {
    "7.3.27": {
      "patches": {
        "7.3.27.0": {
          "sftp_folder": "7_3_27_0",
          "sftp_path": "/ACARS_V7_3/7_3_27_0",
          "status": "pending_approval",
          "discovered_at": "2026-04-03T17:01:12Z",
          "downloaded_at": "2026-04-03T17:01:12Z",
          "approved_at": null,
          "published_at": null
        }
      }
    }
  }
}
```

### State Manager

- Atomic writes: write to `.tmp` file → rename (prevents corruption)
- File locking for concurrent access safety
- Pydantic models validate all state before writing

### Status State Machine

```
discovered → downloaded → pending_approval → approved → published
```

The pipeline tracks each patch folder as a single unit. Download grabs the entire patch folder from SFTP. Approval and publish are manual actions via the UI.

---

## API Endpoints (MVP)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/products` | List products with patch counts by status |
| GET | `/api/patches` | List patches (filterable by product, status) |
| GET | `/api/patches/{product_id}/{patch_id}` | Patch detail with contents |
| POST | `/api/pipeline/scan` | Trigger SFTP scan for new patches |
| POST | `/api/pipeline/fetch/{product_id}/{patch_id}` | Trigger binaries download |
| POST | `/api/patches/{product_id}/{patch_id}/approve` | Approve patch binaries |
| POST | `/api/patches/{product_id}/{patch_id}/publish` | Mark as published |

---

## Key Architecture Patterns

### Pipeline Module Pattern
All pipelines extend `PipelineBase` ABC:
- `id` — unique identifier
- `name` — display name
- `process(patch)` — execute the pipeline for a given patch
- `can_process(patch)` — check if this pipeline applies (e.g., docs checks for DOC/ folder)

Adding a new pipeline = new folder under `pipelines/` + register in orchestrator.

### Integration Module Pattern
SFTP is the first integration. Future integrations (Jira, email, PM tools) follow the same pattern:
- Each integration lives in `integrations/{name}/`
- Configured via environment variables
- Independent lifecycle (can be enabled/disabled)

### File Storage
- All files stay on the filesystem — state files reference paths, never store file contents
- Patch files: `patches/{PRODUCT_ID}/{PATCH_ID}/` preserving SFTP structure
- Templates: `templates/` (bind-mounted)

---

## Critical Existing Files

- `config/pipeline.json` — product definitions, lifecycle, Jira fields, portal settings
- `templates/Flightscape-English-External Business Document.docx` — CAE corporate template (docs pipeline)

---

## Phased Roadmap

### Phase 0 — MVP ← WE ARE HERE
**Goal:** SFTP → discover → download binaries → approve → publish tracking

- JSON state files on disk (no database)
- SFTP integration (paramiko connector + scanner)
- Binaries pipeline (fetch + verify)
- Manual approval workflow via API/UI
- Minimal Next.js dashboard (products, patches, approve/publish)
- Docker Compose (backend + frontend, no DB)
- Docs pipeline stubbed (no DOC/ on SFTP yet)

### Phase 1 — Docs Pipeline
**Goal:** Convert raw release notes to branded CAE documents

- Docx template engine (python-docx): extract body content → inject into CAE template
- DOC/ folder detection during SFTP scan
- Independent docs approval workflow (separate from binaries)
- Release notes file tracking in state files (source path + output path)
- Template management (multiple templates possible)

### Phase 2 — PostgreSQL Migration
**Goal:** Move from JSON files to a proper database for richer data and querying

- PostgreSQL + SQLAlchemy async + Alembic migrations
- Tables: `products`, `patches`, `release_notes`, `pipeline_runs`, `approvals`, `events`
- Migration script: read JSON state files → insert into DB
- Rich content storage for release notes (text, images, tables parsed from docx)
- Full audit trail via append-only `events` table
- JSONB columns for flexible metadata

### Phase 3 — Real-time & Notifications
**Goal:** Push updates to the UI instead of polling

- WebSocket event streaming (FastAPI native)
- In-process async event bus connecting all modules
- Browser notifications for new patches / approval requests
- Live dashboard updates

### Phase 4 — Jira Automation (Partially Complete)
**Goal:** Auto-create Jira tasks when patches are approved

**Confirmed (2026-04-03):**
- Jira Cloud connection working (classic API token + Basic Auth)
- Project: `CFSSOCP` (CFS-ServiceOps-CommPortal, id=10008)
- Issue type: "Release notes, documents & binaries" (id=10163)
- All 10 required fields mapped with confirmed IDs and values
- Dry-run script validated (`scripts/test_jira.py`)
- **Real ticket created & validated** (CFSSOCP-6590) — all fields accepted, attachment uploaded
- **Search API:** Old `/rest/api/3/search` removed (HTTP 410). Use `POST /rest/api/3/search/jql`
- **New/existing detection:** JQL searches by Release Name field (`cf[10563]`), not summary
- **Delete via API:** Not available (403) — must delete manually
- Ticket creation script: `scripts/create_jira_ticket.py`

**Remaining:**
- Write ticket keys back to patch state trackers (`jira_ticket_key`, `jira_ticket_url`, `jira_created_at`)
- Batch processing for multiple simultaneous approvals
- Zip + attach real downloaded binaries to created tickets
- Status polling and state sync

### Phase 5 — Product Control Center
**Goal:** Full operations platform with pluggable pipelines

- Control center dashboard (charts, release velocity, product health)
- Email triage integration (incoming emails trigger scans or workflows)
- Plugin system: register new pipelines and integrations as modules
- PM tool integrations (generic adapter over IntegrationBase)
- LLM-assisted content review and summarization
- User management and role-based access
- Scheduled automation (cron-based pipeline runs)

---

## Verification (MVP)

1. `docker-compose up` → backend + frontend start
2. Open dashboard → products listed with current patch counts
3. Click "Scan SFTP" → new patches discovered, tracker JSONs updated
4. Patches appear in list with `discovered` status
5. Trigger download → patch folder downloaded from SFTP
6. Approve a patch → status changes to `approved`
7. Mark published → status changes to `published`
8. Check `state/patches/ACARS_V8_1.json` → hierarchical state with normalized IDs
9. Re-scan → only new patches added, existing ones untouched
