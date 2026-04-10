# OpsComm Pipeline

## Goal

Automate the ingestion of software releases from an SFTP server for the OpsComm / ACARS product family. The pipeline scans for new patches, downloads them, and presents them for manual approval before publishing to the CAE community portal. This is the first module of a larger Product Control Center platform.

**Current phase:** MVP (Phase 0) **complete** — backend done (5 blocks, 121 tests), frontend done (F1–F5; F6 testing deferred). Next phase is the **docs pipeline** (Zendesk fetch + DOCX template injection) — design captured in [PLAN_DOCS_PIPELINE.md](PLAN_DOCS_PIPELINE.md).

## Tech Stack

- **Backend:** Python + FastAPI
- **Frontend:** React + Vite + Tailwind
- **State:** JSON files on disk (no database for MVP)
- **SFTP:** paramiko
- **Deployment:** Single process — FastAPI serves both API and built frontend static files on one port

## Development Commands

```bash
# Dev mode (two terminals, hot reload)
cd backend && uvicorn app.main:app --reload          # API on :8000
cd frontend && npm run dev                            # Vite on :5173, proxies /api → :8000

# Production mode (one process)
cd frontend && npm run build
cd backend && uvicorn app.main:app                    # serves everything on :8000

# Tests
cd backend && pytest tests/ -v -k "not integration"
```

## Pipeline Flow

```
SFTP scan → discover → download → pending_approval → approved → published
```

Each patch tracks **binaries** and **release notes** independently (separate Jira tickets).

## Project Structure

```
OpsCommDocsPipeline/
├── backend/
│   ├── app/
│   │   ├── config.py              # Pydantic Settings: .env + pipeline.json
│   │   ├── logging_config.py      # Stdout + rotating file logger
│   │   ├── state/
│   │   │   ├── models.py          # Pydantic models (ProductTracker, PatchEntry, etc.)
│   │   │   └── manager.py         # load_tracker(), save_tracker() — atomic writes
│   │   ├── api/                   # FastAPI routers (10 endpoints)
│   │   ├── services/
│   │   │   ├── orchestrator.py    # run_scan() — SFTP → discover → download → update state
│   │   │   └── patch_service.py   # find_patch(), approve_binaries() with two-step save
│   │   ├── pipelines/
│   │   │   ├── base.py            # PipelineBase ABC
│   │   │   ├── binaries/
│   │   │   │   └── fetcher.py     # download_patch() — recursive SFTP download
│   │   │   └── docs/
│   │   │       └── stub.py        # Placeholder — to be replaced by Zendesk fetcher + DOCX converter (see PLAN_DOCS_PIPELINE.md)
│   │   └── integrations/          # sftp/, jira/, (zendesk/ — coming next)
│   ├── tests/                     # pytest — 121 tests passing
│   └── requirements.txt
├── config/pipeline.json           # Products, lifecycle, Jira fields, portal settings
├── state/patches/*.json           # Tracker files — source of truth for state model
├── scripts/                       # Original SFTP/Jira scripts (reference for extraction)
├── product-control-center-mockup.jsx  # React UI mockup (design reference)
├── patches/                       # Downloaded patch files
├── templates/                     # CAE doc template (future)
└── .env                           # SFTP + Jira credentials (never commit)
```

## Key Documents — Read These

| Document | What it covers |
|----------|---------------|
| `PLAN_DOCS_PIPELINE.md` | **Start here for the next phase.** Docs pipeline design: Zendesk fetch + DOCX template injection, two-state-machine model (workflow status + run status), main scan flow, retrigger model, scan history. |
| `HANDOFF.md` | Jira gotchas, Zendesk scraper gotchas, completed backend blocks, completed frontend blocks |
| `ARCHITECTURE.md` | Workflows, API endpoints (10 total), state model, approve flow (two-step save), error handling. **Note:** the docs-pipeline portions (Phase 1, scan-workflow `DOC/` detection) are superseded by `PLAN_DOCS_PIPELINE.md`. |
| `FRONTEND_WORKFLOWS.md` | API response shapes, UI mockups, rendering rules |
| `config/pipeline.json` | All Jira field IDs, values, templates — the actual config used at runtime |
| `state/patches/*.json` | Canonical state model — use this structure, NOT the flat model in scripts |
| `COMPLETED_PLAN_RESTRUCTURE.md` | Historical: original plan for the backend/frontend folder structure (done) |
| `COMPLETED_PLAN_FRONTEND.md` | Historical: original plan for the frontend build blocks F1–F5 (done) |
| `PLAN_FRONTEND_TESTING.md` | Deferred: full frontend test plan for when F6 is picked up |

## Agent Instructions

- **Each block = code + tests + logging + commit.** Don't skip tests or logging.
- **Test before commit:** `cd backend && pytest tests/ -v -k "not integration"` must pass before every push.
- **State model:** Always use the nested structure from `state/patches/*.json` (binaries + release_notes sub-objects). The scripts use an outdated flat model — don't copy it. The docs pipeline adds two new things to this model — see [PLAN_DOCS_PIPELINE.md](PLAN_DOCS_PIPELINE.md) section 3: a `not_found` value on `release_notes.status`, and a `last_run` sub-object on **both** tracks (workflow status and run status are two orthogonal state machines — never put `failed` or `error` in workflow status).
- **Approve endpoint logic:** Empty request body = mark as published (skip Jira). Body with Jira fields = full flow. Same endpoint, no separate routes.
- **Docs pipeline source:** release notes come from **Zendesk**, not from a `DOC/` subfolder on SFTP. Older parts of `ARCHITECTURE.md` mention `DOC/` detection — that approach was dropped. See `PLAN_DOCS_PIPELINE.md`.
