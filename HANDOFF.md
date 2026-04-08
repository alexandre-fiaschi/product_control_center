# Implementation Handoff

**Date:** 2026-04-08
**Author:** Alexandre Fiaschi (assisted by Claude Code)

---

## Jira Gotchas

Field IDs, values, and templates are all in `config/pipeline.json`. Workflows and JQL logic are in `ARCHITECTURE.md`. Below are only the non-obvious traps:

- **Scoped tokens don't work** — only classic API tokens work for this Jira instance. Credential in `.env`: `JIRA_API_TOKEN_NO_SCOPES`
- **Old search endpoint removed** — `POST /rest/api/3/search` returns 410. Use `POST /rest/api/3/search/jql` instead
- **JQL must use exact match** — `cf[10563] = "Version {version}"` not `~` (contains). Using `~` causes false matches (e.g., 8.1.1 matches 8.1.11)
- **Delete via API is 403** — test tickets must be deleted manually from the Jira board
- **Attachment uploaded after ticket creation** — not at creation time. Requires `X-Atlassian-Token: no-check` header
- **CAPTCHA risk** — failed login attempts can trigger CAPTCHA, temporarily blocking API auth

---

## Known Issues — To Fix During Build

1. ~~**State model inconsistency**~~ — **Fixed in Block 2.** Scanner uses nested Pydantic models (binaries + release_notes), not the flat script model.

2. ~~**State writes not atomic**~~ — **Fixed in Block 1.** `save_tracker()` uses `.tmp` → `os.replace()` + `fcntl` locking.

3. **Mockup uses hardcoded data** — Real state is 31 pending binaries, 0 published. Mockup is design reference only — frontend fetches from API.

4. **Mockup timeline uses fake timestamps** — `PatchDetailModal` fabricates steps. **Fix:** Use real per-pipeline timestamps from API response.

5. **Mockup description doesn't recompute** — Editing Release Name or Create/Update/Remove doesn't update description. **Fix:** Add `useEffect` in real component.

6. **Mockup buttons are placeholders** — All `href="#"`, no handlers. Expected — real handlers built during frontend implementation.

---

## Backend Build Blocks

The backend is split into **5 blocks**, each independently buildable, testable, and committable. Each block builds on the previous one. After each block:

1. Run tests → all pass
2. Commit to git
3. Push to GitHub

Each block is scoped so an agent can implement it in one session with full context. The block description includes: what to build, what to extract from existing scripts, what tests to write, what logging to add.

**Reference docs for every block:**
- `ARCHITECTURE.md` — workflows, API endpoints, state model, error handling
- `PLAN_RESTRUCTURE.md` — folder structure, code extraction map, logging spec
- `config/pipeline.json` — product definitions, Jira field mappings
- `state/patches/*.json` — canonical state model (source of truth for data shape)
- `scripts/test_sftp.py` — SFTP logic to extract (NOTE: uses outdated flat state model — adapt to nested binaries/release_notes structure)
- `scripts/test_jira.py` + `scripts/create_jira_ticket.py` — Jira logic to extract

---

### Block 1: Scaffold + Config + State + Models — DONE

**Status:** Complete — 17/17 tests passing.

**What was built:**
- `backend/app/config.py` — Pydantic Settings: loads `.env` + `config/pipeline.json`, exposes `state_dir` / `patches_dir` path properties
- `backend/app/logging_config.py` — stdout + rotating file handler (`logs/pipeline.log`, 5MB, 5 backups)
- `backend/app/state/models.py` — `BinariesState`, `ReleaseNotesState`, `PatchEntry`, `VersionData`, `ProductTracker` matching real tracker JSON shape
- `backend/app/state/manager.py` — `load_tracker()` / `save_tracker()` with atomic `.tmp` → `os.replace()` + `fcntl` file locking
- `backend/tests/` — conftest fixtures, test_config (4), test_models (7), test_state_manager (6)

---

### Block 2: SFTP Integration (connector + scanner + parsers) — DONE

**Status:** Complete — 38 new tests passing (83 total).

**What was built:**
- `backend/app/integrations/sftp/connector.py` — `SFTPConnector` context manager (paramiko), `list_dirs()` with `stat.S_ISDIR` filter
- `backend/app/integrations/sftp/product_parsers.py` — `normalize_patch_id()`, `version_from_patch_id()`, `parse_track_from()`, per-product parse functions (v81/v80/v73)
- `backend/app/integrations/sftp/scanner.py` — `discover_patches()` dispatcher, `discover_v81/v80/v73()`, `update_tracker()` using nested Pydantic models (binaries + release_notes)
- `backend/tests/test_product_parsers.py` (21 tests), `test_scanner.py` (12 tests), `test_sftp_connection.py` (integration, skipped by default)

---

### Block 3: Jira Integration (client + ticket builder + attachment) — DONE

**Status:** Complete — 28 new tests passing (83 total).

**What was built:**
- `backend/app/integrations/jira/client.py` — `JiraClient` class with `search_jql()` (POST `/search/jql`), `create_issue()`, `add_attachment()` (`X-Atlassian-Token: no-check`), `get_myself()`; `JiraError` exception
- `backend/app/integrations/jira/ticket_builder.py` — `text_to_adf()`, `build_binaries_payload()`, `build_docs_payload()` — reads all 10 field IDs/values dynamically from `pipeline.json`
- `backend/app/integrations/jira/attachment.py` — `zip_patch_folder()` (in-memory zip), `upload_attachment()`
- `backend/tests/test_jira_client.py` (10 tests), `test_ticket_builder.py` (10 tests), `test_attachment.py` (3 tests), `test_jira_connection.py` (integration, skipped by default)

---

### Block 4: Services + Pipeline Stubs

**Goal:** Build the service layer that coordinates SFTP scanning and approval workflows. Connects Block 1 (state), Block 2 (SFTP), and Block 3 (Jira) into actual business logic.

**Files to create:**

```
backend/app/services/
├── __init__.py
├── orchestrator.py            # Coordinates scan → discover → download → update state
└── patch_service.py           # find_patch(), status transitions, approve workflows

backend/app/pipelines/
├── __init__.py
├── base.py                    # PipelineBase ABC
├── binaries/
│   ├── __init__.py
│   ├── fetcher.py             # Download patch folder contents from SFTP
│   └── processor.py           # Post-download verification
└── docs/
    ├── __init__.py
    └── stub.py                # Placeholder — returns "skipped"

backend/tests/
├── test_orchestrator.py
├── test_patch_service.py
└── test_fetcher.py
```

**What to build:**

- **`patch_service.py`** — `find_patch()`, `validate_transition()`, `approve_binaries(product_id, patch_id, jira_fields=None)`: empty jira_fields → mark published directly (already on portal); with jira_fields → full flow with **two-step save** (save after approved, save after published). `approve_docs()` same pattern.
- **`orchestrator.py`** — `run_scan(product_ids=None)`: connect SFTP → discover → download → update tracker. `run_scan_product()` for single product.
- **`pipelines/binaries/fetcher.py`** — `download_patch(sftp, sftp_path, local_path)`: downloads full patch folder, preserves structure.
- **`pipelines/docs/stub.py`** — returns `{"status": "skipped"}`. Placeholder for Phase 1.

**Logging:** `services.orchestrator` — INFO for run start/complete, ERROR for failures. `services.patch_service` — INFO for approvals/transitions/mark-published, ERROR for failures. `pipelines.binaries.fetcher` — INFO for download start/complete, ERROR for failures.

**Tests:**
- `test_patch_service.py` (unit, mocked Jira+state): full flow works, invalid transitions rejected, empty jira_fields → mark published (no Jira call), Jira failure → stays "approved", two-step save verified
- `test_orchestrator.py` (unit, mocked SFTP): discovers new patches, idempotent, partial failure handled
- `test_fetcher.py` (unit, mocked SFTP): downloads to correct path, creates dirs, handles empty folder

**Verify:** `cd backend && pytest tests/ -v -k "not integration"`

---

### Block 5: FastAPI App + API Endpoints

**Goal:** Wire everything together with FastAPI. Create all 10 API endpoints, serve frontend static files, add structured error responses. After this block, the backend is fully functional.

**Files to create:**

```
backend/app/
├── main.py                    # FastAPI app, lifespan, static files mount
├── api/
│   ├── __init__.py
│   ├── products.py            # GET /api/products, /api/products/{product_id}
│   ├── patches.py             # GET /api/patches, approve endpoints
│   ├── pipeline.py            # POST /api/pipeline/scan, GET /api/dashboard/summary
│   └── errors.py              # Structured error response model + exception handlers

backend/tests/
├── test_api_products.py
├── test_api_patches.py
├── test_api_pipeline.py
└── test_api_dashboard.py
```

**What to build:**

- **`main.py`** — FastAPI app with lifespan, router includes, mounts `frontend/dist/` if it exists, calls `logging_config.setup()`. No CORS needed.
- **`api/products.py`** — `GET /api/products` (list with counts), `GET /api/products/{product_id}` (detail with versions)
- **`api/patches.py`** — `GET /api/patches` (actionable+history split), `GET /api/patches/{product_id}`, `GET /api/patches/{product_id}/{patch_id}`, `POST .../binaries/approve` (with body=Jira flow, empty=mark published), `POST .../docs/approve`
- **`api/pipeline.py`** — `POST /api/pipeline/scan`, `POST /api/pipeline/scan/{product_id}`, `GET /api/dashboard/summary`
- **`api/errors.py`** — `PipelineError` exception + handler returning `{ error, detail, patch_id, pipeline, step, timestamp }`

**Logging:** `api.*` loggers — INFO for scan triggers/approvals, ERROR for failures.

**Tests (FastAPI TestClient, mocked services):**
- `test_api_products.py`: correct shape, 404 for nonexistent
- `test_api_patches.py`: actionable/history split, approve with body vs empty body, already-published → 400
- `test_api_pipeline.py`: scan returns results
- `test_api_dashboard.py`: correct counts

**Verify:**
```bash
cd backend && pytest tests/ -v -k "not integration"
cd backend && uvicorn app.main:app --reload
curl http://localhost:8000/api/products
curl http://localhost:8000/api/dashboard/summary
```

---

## Block Summary

| Block | What | Depends on | Status |
|-------|------|------------|--------|
| 1 | Scaffold + Config + State + Models | Nothing | **DONE** |
| 2 | SFTP Integration | Block 1 | **DONE** |
| 3 | Jira Integration | Block 1 | **DONE** |
| 4 | Services + Pipeline Stubs | Blocks 1, 2, 3 |
| 5 | FastAPI App + API Endpoints | Block 4 |

**Blocks 2 and 3 can be built in parallel** — they both depend on Block 1 but not on each other.

### Git flow per block

```
1. Agent implements block (code + tests + logging)
2. Run: cd backend && pytest tests/ -v -k "not integration"
3. All tests pass
4. git commit + git push
```

### After all 5 blocks

```bash
cd backend && pytest tests/ -v -k "not integration"
cd backend && uvicorn app.main:app --reload
curl http://localhost:8000/api/products
curl http://localhost:8000/api/dashboard/summary
curl -X POST http://localhost:8000/api/pipeline/scan
```

Backend is complete. Frontend build starts next.
