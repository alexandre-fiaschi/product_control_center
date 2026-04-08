# Implementation Handoff

**Date:** 2026-04-08
**Author:** Alexandre Fiaschi (assisted by Claude Code)

---

## Jira Integration Reference

### Auth

- **Method:** Basic Auth (email + classic API token) against `https://caeglobal.atlassian.net`
- **Credentials in `.env`:** `JIRA_EMAIL`, `JIRA_API_TOKEN_NO_SCOPES`
- Scoped tokens do NOT work for this instance — use the classic token only
- CAPTCHA can be triggered after failed login attempts, temporarily blocking API auth
- Token expiration: check at https://id.atlassian.com/manage-profile/security/api-tokens

### Project & Issue Type

- Project key: **`CFSSOCP`** (id=10008, `CFS-ServiceOps-CommPortal`)
- Issue type: **"Release notes, documents & binaries"** (id=`10163`)
- Same issue type for both binaries AND docs (different field values)

### Required Fields

| Field | Field ID | Type | Value (Binaries Pipeline) |
|-------|----------|------|---------------------------|
| Project | `project` | project | `{"key": "CFSSOCP"}` |
| Issue Type | `issuetype` | issuetype | `{"id": "10163"}` |
| Summary | `summary` | string | `"Add Release Version {patch_id}"` |
| Client | `customfield_10328` | array | `[{"value": "Flightscape"}]` |
| Environment | `customfield_10538` | option | `{"value": "All the three"}` |
| Product Name | `customfield_10562` | string | `"CAE® Operations Communication Manager"` |
| Release Name | `customfield_10563` | string | `"Version {major.minor.patch}"` (e.g., "Version 8.1.11") |
| Release Type | `customfield_10616` | option | `{"value": "Version"}` |
| Release Approval | `customfield_10617` | option | `{"value": "Users should not request approval to access or download files on this release"}` |
| Create/Update/Remove | `customfield_10618` | option | `"New CAE Portal Release"` or `"Existing CAE Portal Release"` |

Optional: **Description** (ADF format), **Attachment** (zip uploaded after ticket creation).

### Description Template

```
Hi Team,

I have this binaries for the release {version} that should all be added in a [new/existing] folder '{Release Name}'.

Please contact me for any questions you may have.

Thank you very much,
```

### Attachment Workflow

1. Zip binaries as `{patch_id}.zip` (e.g., `8.1.11.0.zip`) — always full patch ID
2. Upload via `POST /rest/api/3/issue/{ticket_key}/attachments`
3. Header: `X-Atlassian-Token: no-check`
4. Content-Type: `multipart/form-data`

### Jira API Endpoints

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| Auth test | GET | `/rest/api/3/myself` | |
| Create issue | POST | `/rest/api/3/issue` | |
| Get issue | GET | `/rest/api/3/issue/{key}` | |
| Add attachment | POST | `/rest/api/3/issue/{key}/attachments` | |
| Search (JQL) | POST | `/rest/api/3/search/jql` | Old `/search` returns 410 |
| Delete issue | DELETE | `/rest/api/3/issue/{key}` | 403 — no permission |

All endpoints use Basic Auth: `email:classic_api_token`.

**JQL for new/existing detection:** `project = CFSSOCP AND cf[10563] = "Version {version}"` (exact match, not `~` contains).

### Constraints

- Delete via API not available (403) — must delete tickets manually
- Docs pipeline may use different Release Type values (not always "Version") — binaries-specific for now
- Token has full account permissions — never commit `.env`

---

## Known Issues — To Fix During Build

1. **State model inconsistency** — `test_sftp.py` uses flat `patch['status']`, but tracker JSONs use nested `binaries.status` / `release_notes.status`. **Fix:** Use tracker JSON structure as source of truth when building backend modules.

2. **State writes not atomic** — Scripts use plain `json.dump()`. **Fix:** Implement write-to-`.tmp`-then-rename in `backend/app/state/manager.py`.

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

### Block 1: Scaffold + Config + State + Models

**Goal:** Create the backend folder structure, config loading, state management, and Pydantic models. After this block, the backend can load `.env`, read `pipeline.json`, and read/write tracker JSON files with atomic saves.

**Files to create:**

```
backend/
├── app/
│   ├── __init__.py
│   ├── config.py                  # Pydantic Settings: loads .env + pipeline.json
│   ├── logging_config.py          # Logging setup: stdout + rotating file
│   ├── state/
│   │   ├── __init__.py
│   │   ├── models.py              # Pydantic models matching state/patches/*.json
│   │   └── manager.py             # load_tracker(), save_tracker() with atomic writes
│   ├── api/__init__.py            # Empty — needed for block 2+
│   ├── services/__init__.py
│   ├── pipelines/__init__.py
│   └── integrations/__init__.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Shared fixtures (tmp dirs, sample trackers)
│   ├── test_config.py
│   ├── test_models.py
│   └── test_state_manager.py
└── requirements.txt
```

**What to build:**

- **`config.py`** — Pydantic Settings: loads `.env` (SFTP_HOST, SFTP_PORT, SFTP_USERNAME, SFTP_PASSWORD, SFTP_KEY_PATH, JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN_NO_SCOPES) + loads `config/pipeline.json` at startup. Resolves paths relative to project root (one level up from `backend/`).
- **`logging_config.py`** — Format: `[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s`. Stdout + rotating file (`logs/pipeline.log`, 5MB, 5 backups).
- **`state/models.py`** — Pydantic models matching **actual tracker JSON files** (not the scripts): `BinariesState`, `ReleaseNotesState`, `PatchEntry`, `VersionData`, `ProductTracker`.
- **`state/manager.py`** — Extract from `scripts/test_sftp.py` lines 187–204, then improve: `load_tracker(product_id)`, `save_tracker(tracker)` with atomic write (`.tmp` → rename), file locking with `fcntl`.

**Logging:** `state.manager` logger — INFO for load/save, ERROR for failures, WARNING for missing tracker files.

**Tests:**
- `test_config.py`: config loads with valid .env, missing vars raise errors
- `test_models.py`: validate PatchEntry against real tracker JSON, reject invalid statuses, optional fields default to null
- `test_state_manager.py`: load existing → correct structure; load missing → empty tracker; save + reload round-trips; atomic write uses .tmp then rename

**Verify:** `cd backend && pip install -r requirements.txt && pytest tests/ -v`

---

### Block 2: SFTP Integration (connector + scanner + parsers)

**Goal:** Extract all SFTP logic from `scripts/test_sftp.py` into proper modules. After this block, the backend can connect to SFTP, discover patches for all 3 products, normalize folder names, and update tracker state.

**Files to create:**

```
backend/app/integrations/sftp/
├── __init__.py
├── connector.py           # SFTPConnector class
├── product_parsers.py     # normalize_patch_id(), version parsing, track_from filtering
└── scanner.py             # discover_patches() per product

backend/tests/
├── test_product_parsers.py
├── test_scanner.py            # Unit tests with mocked SFTP
└── test_sftp_connection.py    # Integration test (hits real SFTP, run manually)
```

**What to extract:**

- **`connector.py`** — from `test_sftp.py` lines 33–41: `SFTPConnector` class with context manager, uses config from Block 1. `list_dirs(path)` method from lines 44–51.
- **`product_parsers.py`** — from `test_sftp.py` lines 57–121: `normalize_patch_id()`, `version_from_patch_id()`, `parse_track_from()`, all per-product parsing functions.
- **`scanner.py`** — from `test_sftp.py` lines 126–182: `discover_patches()`, `update_tracker()`. **IMPORTANT:** Must create patches with the **nested** state model (binaries + release_notes sub-objects), NOT the flat model from the script.

**Logging:** `sftp.connector` — INFO for open/close, ERROR for connection failures, DEBUG for directory listings. `sftp.scanner` — INFO for scan start/results, WARNING for skipped duplicates, DEBUG for normalization.

**Tests:**
- `test_product_parsers.py` (unit): all normalize cases (v8.1.0.0→8.1.0.0, 8_0_28_1→8.0.28.1, 7_3_27_7→7.3.27.7, garbage→None), version_from_patch_id, parse_track_from
- `test_scanner.py` (unit, mocked SFTP): update_tracker creates nested structure, idempotent, respects track_from
- `test_sftp_connection.py` (integration, `@pytest.mark.integration` — skipped by default)

**Verify:** `cd backend && pytest tests/ -v -k "not integration"`

---

### Block 3: Jira Integration (client + ticket builder + attachment)

**Goal:** Extract all Jira logic from `scripts/test_jira.py` and `scripts/create_jira_ticket.py` into proper modules. After this block, the backend can authenticate with Jira, search by JQL, create tickets, and upload attachments.

**Files to create:**

```
backend/app/integrations/jira/
├── __init__.py
├── client.py              # JiraClient class (requests + Basic Auth)
├── ticket_builder.py      # Build Jira payloads from patch state
└── attachment.py          # Zip folder + upload to Jira ticket

backend/tests/
├── test_jira_client.py        # Unit tests with mocked HTTP
├── test_ticket_builder.py     # Payload construction tests
├── test_attachment.py         # Zip creation tests
└── test_jira_connection.py    # Integration test (hits real Jira, run manually)
```

**What to extract:**

- **`client.py`** — `JiraClient` class: `search_jql()` → POST to `/rest/api/3/search/jql` (NOT old `/search`), `create_issue()`, `add_attachment()` with `X-Atlassian-Token: no-check` header.
- **`ticket_builder.py`** — `text_to_adf()`, `build_binaries_payload()`, `build_docs_payload()`. All 10 required fields from the Jira reference section above.
- **`attachment.py`** — `zip_patch_folder(local_path, patch_id)` → creates `{patch_id}.zip`.

**Logging:** `jira.client` — INFO for search results/ticket creation/uploads, WARNING for unexpected status codes, ERROR for failures, DEBUG for request/response details.

**Tests:**
- `test_jira_client.py` (unit, mocked HTTP): successful create → key+url, 401 → auth error, 400 → field error, correct endpoint used
- `test_ticket_builder.py` (unit): ADF structure, new/existing folder logic, all 10 fields present, summary template
- `test_attachment.py` (unit): zip created at correct path, contains correct files, handles empty folder
- `test_jira_connection.py` (integration, `@pytest.mark.integration`)

**Verify:** `cd backend && pytest tests/ -v -k "not integration"`

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

| Block | What | Depends on |
|-------|------|------------|
| 1 | Scaffold + Config + State + Models | Nothing |
| 2 | SFTP Integration | Block 1 |
| 3 | Jira Integration | Block 1 |
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
