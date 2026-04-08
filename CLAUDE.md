# OpsComm Pipeline

## Goal

Automate the ingestion of software releases from an SFTP server for the OpsComm / ACARS product family. The pipeline scans for new patches, downloads them, and presents them for manual approval before publishing to the CAE community portal. This is the first module of a larger Product Control Center platform.

**Current phase:** MVP (Phase 0) — SFTP discovery + download + manual approval via API/UI.

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
│   │   ├── api/                   # (Block 5)
│   │   ├── services/
│   │   │   ├── orchestrator.py    # run_scan() — SFTP → discover → download → update state
│   │   │   └── patch_service.py   # find_patch(), approve_binaries() with two-step save
│   │   ├── pipelines/
│   │   │   ├── base.py            # PipelineBase ABC
│   │   │   ├── binaries/
│   │   │   │   └── fetcher.py     # download_patch() — recursive SFTP download
│   │   │   └── docs/
│   │   │       └── stub.py        # Placeholder — returns "skipped"
│   │   └── integrations/          # (Blocks 2 + 3)
│   ├── tests/                     # pytest — 99 tests passing
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
| `HANDOFF.md` | **Start here for building.** Jira gotchas, known issues, and 5 backend build blocks with tests/logging per block |
| `ARCHITECTURE.md` | Workflows, API endpoints (10 total), state model, approve flow (two-step save), error handling |
| `PLAN_RESTRUCTURE.md` | Target folder structure for `backend/` + `frontend/`, code extraction map from scripts |
| `PLAN_FRONTEND.md` | Frontend components, views, API client, data flow, mockup line references |
| `FRONTEND_WORKFLOWS.md` | API response shapes, UI mockups, rendering rules |
| `config/pipeline.json` | All Jira field IDs, values, templates — the actual config used at runtime |
| `state/patches/*.json` | Canonical state model — use this structure, NOT the flat model in scripts |

## Agent Instructions

- **Parallelize when possible.** Backend blocks 2 (SFTP) and 3 (Jira) can be built in parallel — they both depend on block 1 but not on each other. If you can run multiple agents, do it.
- **Each block = code + tests + logging + commit.** Don't skip tests or logging — they're specified per block in `HANDOFF.md`.
- **Test before commit:** `cd backend && pytest tests/ -v -k "not integration"` must pass before every push.
- **State model:** Always use the nested structure from `state/patches/*.json` (binaries + release_notes sub-objects). The scripts use an outdated flat model — don't copy it.
- **Approve endpoint logic:** Empty request body = mark as published (skip Jira). Body with Jira fields = full flow. Same endpoint, no separate routes.
