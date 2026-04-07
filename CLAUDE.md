# OpsComm Pipeline

## Goal

Automate the ingestion of software releases from an SFTP server for the OpsComm / ACARS product family. The pipeline scans for new patches, downloads them, and presents them for manual approval before publishing to the CAE community portal. This is the first module of a larger Product Control Center platform.

**Current phase:** MVP (Phase 0) — SFTP discovery + download + manual approval via API/UI.
**Future:** docs conversion, Jira automation, email triggers, pluggable pipeline architecture.

## Tech Stack

- **Backend:** Python + FastAPI (not yet built)
- **Frontend:** Next.js + Tailwind (not yet built)
- **State:** JSON files on disk (no database for MVP)
- **SFTP:** paramiko
- **Containerization:** Docker Compose (planned)

## Tracked Products

| Product ID | SFTP Path | Structure | Track From |
|------------|-----------|-----------|------------|
| ACARS_V8_1 | /ACARS_V8_1 | hierarchical (2 levels) | ALL |
| ACARS_V8_0 | /ACARS_V8_0 | hierarchical (2 levels) | 8_0_28 |
| ACARS_V7_3 | /ACARS_V7_3 | flat (1 level) | 7_3_27_0 |

All patch IDs normalized to dotted format (e.g., `7_3_27_7` -> `7.3.27.7`).
All products stored hierarchically in tracker as `version/patch`.

## Project Structure

```
OpsCommDocsPipeline/
├── .env                          # SFTP + Jira credentials (never commit)
├── .gitignore                    # Protects .env, venv, snapshots, __pycache__
├── ARCHITECTURE.md               # Detailed architecture and implementation plan
├── CLAUDE.md                     # This file — project overview for Claude
├── PROGRESS.md                   # What's been done, what's next
├── HANDOFF_JIRA_INTEGRATION.md   # Jira integration handoff — fields, endpoints, findings
├── OpsComm Pipeline - Project Documentation.md  # Original project documentation
│
├── config/
│   └── pipeline.json             # Products, lifecycle, Jira fields, portal settings
│
├── state/
│   └── patches/
│       ├── ACARS_V8_1.json       # V8.1 tracker — 24 patches across 12 versions
│       ├── ACARS_V8_0.json       # V8.0 tracker — 5 patches across 3 versions
│       └── ACARS_V7_3.json       # V7.3 tracker — 5 patches in 1 version
│
├── scripts/
│   ├── test_sftp.py              # SFTP dry run: scan, simulate download, approval gate
│   ├── test_jira.py              # Jira dry run: auth, fields, payload validation
│   └── create_jira_ticket.py     # Creates real Jira ticket + attachment for a patch ID
│
├── patches/                      # Downloaded patch files go here (empty for now)
├── templates/
│   └── Flightscape-English-External Business Document.docx  # CAE doc template (future)
├── docs example/                 # Example docs for reference
└── venv/                         # Python virtual environment (paramiko, python-dotenv, requests)
```

## Pipeline Flow

```
SFTP scan -> discover new patches -> download patch folder -> pending_approval -> approved -> published
```

Each patch tracks **binaries** and **release notes** independently:
- **Binaries:** `discovered -> downloaded -> pending_approval -> approved -> published`
- **Release notes:** `not_started -> discovered -> downloaded -> converted -> pending_approval -> approved -> published`

## Key Decisions

- **No database for MVP** — JSON tracker files under `state/patches/`, one per product
- **Patch folder is the unit of work** — download the whole folder, don't inspect contents
- **Hierarchical tracking even for flat SFTP** — V7.3 is flat on SFTP but stored as version/patch
- **Idempotent scanning** — re-running scan only adds new patches, never duplicates
- **track_from cutoff** — older patches already published, no need to re-process

## Jira Integration

- **Auth:** Basic Auth with classic API token (no scopes) — scoped tokens don't work
- **Project:** `CFSSOCP` (id=10008), Issue type: `10163` ("Release notes, documents & binaries")
- **Search API:** `POST /rest/api/3/search/jql` — old `/search` endpoint removed (HTTP 410)
- **New/existing detection:** JQL `project = CFSSOCP AND cf[10563] ~ "{version}"` (Release Name field)
- **Delete via API:** Not available (403) — must delete manually
- **Ticket creation + attachment:** Confirmed working

## SFTP Naming Quirks

- V8.1 patches: mixed `v` prefix (`v8.1.0.0`) and no prefix (`8.1.10.0`)
- V8.0 version folders: `8_0_{minor}` not `ACARS_V8_0_{minor}`
- V7.3: flat on SFTP, version derived from folder name
- All normalized to dotted format in tracker
