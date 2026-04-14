# OpsComm Pipeline

## Goal

Automate the ingestion of software releases from an SFTP server for the OpsComm / ACARS product family. The pipeline scans for new patches, downloads them, and presents them for manual approval before publishing to the CAE community portal. This is the first module of a larger Product Control Center platform.

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

## Dev Mode vs Prod Mode

External services are gated by `enabled` flags in `config/pipeline.json`. In dev mode, all flags are `false` — no real API calls are made. Flip to `true` when ready for production.

| Service | Config flag | Dev mode (false) | Prod mode (true) |
|---------|------------|------------------|-------------------|
| **Jira** | `jira.enabled` | No ticket creation | Creates real Jira tickets |
| **Zendesk** | `docs.enabled` | No PDF fetching | Fetches PDFs from Zendesk |
| **Claude** | `claude.enabled` | Orchestrator skips extraction. Script `--mode claude` still works (uses local cache or `--no-cache` for a real call). | Orchestrator calls Claude API during scans |
| **SFTP** | *(always on when credentials are in `.env`)* | Scans real SFTP | Same |

Cached extraction results (`.cache/claude/<hash>.json`) act as mock data in dev mode — the script reuses them without API calls. Only `--no-cache` triggers a real Claude call.

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

## Output Style (strict — applies to every conversation in this project)

Be terse when explaining. Be thorough when implementing. Two different modes:

**Explaining / talking with Alex:**
- Lead with the answer or action. No preamble.
- Don't restate the question. Don't summarize what you just did — the diff and tool results already show it.
- One short paragraph per point. No filler ("Great!", "Let me…", "I'll now…", "Perfect!").
- No tables, bullet lists, or headings unless the answer genuinely needs structure or Alex asked for them.
- When proposing options, number them (1, 2, 3) and one line each. No multi-paragraph pitches.
- If you can say it in one sentence, use one sentence.
- Only expand when Alex asks "explain more", "details", or "why".
- Goal: keep the terminal uncluttered so Alex can read fast and ask follow-ups.

**Implementing code:**
- Don't be lazy. Read the relevant files, understand the existing patterns, write complete and correct code.
- Tests, logging, error handling — all required per the agent rules above.
- Verbose code when needed is fine. Verbose chat is not.


1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

State your assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask.

2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

3. Surgical Changes
Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting.
Don't refactor things that aren't broken.
Match existing style, even if you'd do it differently.
If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused.
Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.

4. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

"Add validation" → "Write tests for invalid inputs, then make them pass"
"Fix the bug" → "Write a test that reproduces it, then make it pass"
"Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

