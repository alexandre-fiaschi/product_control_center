# OpsComm Pipeline — Progress Tracker

## Phase 0 — MVP

### Completed (2026-04-03)

- [x] **SFTP connection tested** — paramiko connects to SFTP server successfully
- [x] **SFTP folder structure explored** — full tree snapshot saved at depth 2 and 3
- [x] **Folder naming patterns validated** — confirmed real naming vs documented assumptions
  - V8.1: mixed `v` prefix (early) and no prefix (later), dots as separators
  - V8.0: underscore separators, version folders are `8_0_{minor}` (not `ACARS_V8_0_{minor}`)
  - V7.3: flat structure confirmed for tracked range, underscore separators, no prefix
- [x] **Product IDs unified** — all three products use `ACARS_V{major}_{minor}` format
- [x] **Tracking cutoffs defined**
  - ACARS_V8_1: track ALL patches
  - ACARS_V8_0: track from `8_0_28` onwards
  - ACARS_V7_3: track from `7_3_27_0` onwards
- [x] **Version normalization implemented** — all folder names normalize to dotted format (e.g., `7_3_27_7` -> `7.3.27.7`, `v8.1.9.1` -> `8.1.9.1`)
- [x] **Hierarchical tracker structure** — even V7.3 (flat on SFTP) stores as `version/patch` (e.g., `7.3.27/7.3.27.7`)
- [x] **Per-product tracker JSONs** — `state/patches/{PRODUCT_ID}.json` created and validated
- [x] **Idempotent scanning** — re-running the scan detects no new patches (only adds new ones)
- [x] **Pipeline dry run** — scan -> download simulation -> approval gate working end-to-end
- [x] **Config files updated**
  - `config/pipeline.json` — products, lifecycle, Jira fields, portal settings (merged from pipeline_flow.json)
- [x] **Python venv** — set up with paramiko + python-dotenv
- [x] **.gitignore** — created to protect .env, venv, snapshots

### Current patch counts (from first scan)

| Product | Versions | Patches | Status |
|---------|----------|---------|--------|
| ACARS V8.1 | 12 | 24 | All pending_approval |
| ACARS V8.0 | 3 | 5 | All pending_approval |
| ACARS V7.3 | 1 | 5 | All pending_approval |
| **Total** | **16** | **34** | |

### Completed — Jira Integration (2026-04-03)

- [x] **Jira API token created** — classic token (no scopes), Basic Auth confirmed working
- [x] **Project key confirmed** — `CFSSOCP` (CFS-ServiceOps-CommPortal, id=10008)
  - Originally documented as CFSSOCF — corrected to CFSSOCP
- [x] **Issue type identified** — "Release notes, documents & binaries" (id=10163)
- [x] **All required fields mapped** — 10 required fields with confirmed IDs and values:
  - Client (`customfield_10328`): Flightscape
  - Environment (`customfield_10538`): All the three
  - Product Name (`customfield_10562`): CAE® Operations Communication Manager
  - Release Name (`customfield_10563`): Version {major.minor.patch}
  - Release Type (`customfield_10616`): Version
  - Release Approval (`customfield_10617`): Users should not request approval...
  - Create/Update/Remove (`customfield_10618`): New/Existing CAE Portal Release
- [x] **Description template defined** — with new/existing folder logic
- [x] **Attachment workflow documented** — zip + POST after ticket creation
- [x] **Dry-run script created** — `scripts/test_jira.py` validates full payload
- [x] **`requests` library installed** in venv
- [x] **Scoped tokens tested and ruled out** — only classic tokens work for this instance

### Completed — Jira Ticket Validation (2026-04-03, Session 2)

- [x] **Real test ticket created** — CFSSOCP-6590 for patch 8.1.11.0, all fields accepted
- [x] **Attachment upload confirmed** — test zip uploaded successfully
- [x] **Search API migration** — old `/rest/api/3/search` removed (HTTP 410), new endpoint: `POST /rest/api/3/search/jql`
- [x] **New/existing folder JQL corrected** — search by Release Name field (`cf[10563]`), not summary
- [x] **`scripts/create_jira_ticket.py` created** — takes `--patch-id`, creates ticket, uploads test attachment
- [x] **Existing ticket inspected** — CFSSOCP-5824 fields compared with our new format, decided to keep new format
- [x] **Delete via API tested** — 403, must delete manually from board

### Completed — Backend Blocks 1-4 (2026-04-08)

- [x] **Block 1: Scaffold + Config + State + Models** — Pydantic Settings, atomic state manager, 17 tests
- [x] **Block 2: SFTP Integration** — SFTPConnector, product parsers, scanner, 38 tests
- [x] **Block 3: Jira Integration** — JiraClient, ticket builder, attachment handler, 28 tests
- [x] **Block 4: Services + Pipeline Stubs** — orchestrator (scan workflow), patch_service (approve with two-step save), binaries fetcher, docs stub, 16 tests
- **Total: 99 tests passing** (`cd backend && pytest tests/ -v -k "not integration"`)

### Completed — Block 5 + Frontend (2026-04-08 → 2026-04-10)

- [x] **Block 5: FastAPI App + API Endpoints** — 10 endpoints, error handling, 22 tests added (total **121 tests passing**)
- [x] **Frontend F1: Scaffold + Shared Code** — Vite, theme tokens, types, API client
- [x] **Frontend F2: Layout + Dashboard** — sidebar, header, summary cards, product cards
- [x] **Frontend F3: Pipeline View** — filter bar, actionable + history tables
- [x] **Frontend F4: Modals + Actions** — patch detail modal, Jira approval modal (currently dry-run)
- [x] **Frontend F5: Polish** — loading skeletons, error toasts, sidebar animation
- [x] **Zendesk scraper prototype** — `scripts/test_zendesk_scraper.py` validated against `cyberjetsupport.zendesk.com` (curl_cffi + legacy `/access/login`)

### Deferred

- [ ] Frontend F6: Testing — full plan saved in `PLAN_FRONTEND_TESTING.md`
- [ ] Docker setup

### Docs pipeline progress

- [x] Unit 9: side-by-side review view (2026-04-20) — new `DocsReviewView` modal, `preview.pdf` + `open-in-word` backend endpoints, `exporter.py` module (reused by Unit 10), LibreOffice brew install. 306 backend tests passing. Button-enablement loosened to open the review gate from `converted` state. Surfaced a DOCX defect: Unit 5's `render_release_notes()` leaves a stale TOC field cache → Word auto-regenerates (correct), LibreOffice uses the cached text (stale template entries). Tracked as Unit 11.
- [ ] Unit 10: DOCX → PDF on approval + Jira attach
- [ ] Unit 11 (new): fix stale TOC cache in `render_release_notes()` — blocks Unit 10's final PDF quality

### Next phase — Docs pipeline

Full design captured in [`PLAN_DOCS_PIPELINE.md`](PLAN_DOCS_PIPELINE.md). Key decisions:
- Release notes come from **Zendesk**, not from SFTP `DOC/` folders (the original assumption was dropped)
- New status value `not_found` added to `ReleaseNotesState`
- New `last_run` sub-object on both `BinariesState` and `ReleaseNotesState` (workflow status + run status as two orthogonal state machines)
- Three-pass main scan (SFTP discovery → binaries pass → docs pass)
- Auto-fetch acts on `not_started` only; `not_found` recovery is manual button (or future email webhook) — never blind cron polling
- Targeted refetch endpoint shared between UI button and future webhook
- Persisted scan history in `state/scans/`

---

## Key files

| File | Purpose |
|------|---------|
| `.env` | SFTP credentials (not committed) |
| `config/pipeline.json` | Products, lifecycle, Jira fields, portal settings |
| `state/patches/ACARS_V8_1.json` | V8.1 tracker (24 patches) |
| `state/patches/ACARS_V8_0.json` | V8.0 tracker (5 patches) |
| `state/patches/ACARS_V7_3.json` | V7.3 tracker (5 patches) |
| `scripts/test_sftp.py` | SFTP dry run script (scan + simulate) |
| `scripts/test_jira.py` | Jira connection dry run (auth + fields + payload) |
| `scripts/create_jira_ticket.py` | Creates real Jira ticket + attachment for a patch ID |
| `scripts/sftp_snapshot_MAX_DEPTH2.txt` | Full SFTP tree snapshot |
| `HANDOFF.md` | Implementation handoff — Jira reference, backend build blocks, known issues |
