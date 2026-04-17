# Implementation Handoff

**Date:** 2026-04-08 (last updated 2026-04-17)
**Author:** Alexandre Fiaschi (assisted by Claude Code)

**Status:** Backend complete (5 blocks, 121 tests). Frontend complete F1–F5 (F6 testing deferred). Docs pipeline: **Units 0–6 done**. Unit 4 verdict is **go** on the Claude-extraction path (Unit 4.5). Unit 5 wires `extract_release_notes` and `render_release_notes` into the orchestrator as Pass 4 + Pass 5. Unit 6 adds a 409 guard on `POST /pipeline/scan`, durable scan history under `state/scans/`, and two new refetch endpoints (targeted + bulk) for recovering from `not_found` release notes. 276 backend tests passing. Design in [PLAN_DOCS_PIPELINE.md](PLAN_DOCS_PIPELINE.md). Next up is Unit 7 (file serving endpoints for the Unit 9 review view).

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

## Zendesk Scraper Gotchas

The release-notes scraper for `cyberjetsupport.zendesk.com` lives at `scripts/test_zendesk_scraper.py`. It downloads PDF release notes for ACARS 7.3 / 8.0 / 8.1 from the help center. Validated end-to-end on 2026-04-10. Non-obvious traps:

- **Cloudflare blocks `requests`** — the help center is behind a Cloudflare JS challenge ("Just a moment...") that returns 403 to plain `requests.Session`. Use `curl_cffi` with `impersonate="chrome"` — it presents a real Chrome TLS fingerprint and gets through. Pure Python, no browser. `pip install curl_cffi`.
- **Don't override the User-Agent on a curl_cffi session** — `impersonate=` sets UA + TLS fingerprint together. Setting a custom UA desyncs them and Cloudflare blocks again.
- **`curl_cffi` Response is not a context manager** — `with session.get(..., stream=True) as r:` raises TypeError. Call `r.close()` in a `finally` block instead. `iter_content(chunk_size=...)` works the same as `requests`.
- **New Next.js auth SPA at `/auth/v3/signin`** — `/hc/en-gb/signin` redirects there. The form has no `action` attribute and login submission happens via bundled JS. **Workaround:** scrape the `authenticity_token` hidden input from the SPA HTML, then POST directly to the legacy `/access/login` endpoint with the classic form payload (`utf8`, `authenticity_token`, `user[email]`, `user[password]`, `return_to`, `commit`). The legacy backend still accepts it — much simpler than reverse-engineering the SPA bundle.
- **Required POST headers** — `Referer: .../auth/v3/signin`, `Origin: https://<sub>.zendesk.com`, `Content-Type: application/x-www-form-urlencoded`. Missing the Referer can cause silent rejection.
- **Auth success marker** — Zendesk sets a `_zendesk_authenticated` cookie after successful login. Cheap, reliable check beyond just URL inspection.
- **PDF attachments live at `/hc/en-gb/article_attachments/<id>`** — the visible link text on the article page is the actual filename (e.g. `8.1.12.0 - Release Notes.pdf`); use it as the saved filename, not the URL basename (which is just the numeric ID).
- **Output target is gitignored** — PDFs land in `docs_example/<branch>/zendesk_pdf_download/<article>/`. The whole `docs_example/` tree is in `.gitignore` so binaries never enter git.
- **Polite throttling matters** — random 0.5–1.5s sleep between every request. We're scraping our vendor's portal, behave like a human.
- **Version cutoff** — current iteration only fetches 8.1 articles ≥ `8.1.10` (default). 7.3 / 8.0 cutoffs are unset until product team confirms.

Run `python scripts/test_zendesk_scraper.py --check-auth --verbose` to verify auth without crawling. See the script docstring for full CLI usage.

---

## DOCX Conversion Prototype Gotchas (Unit 4 — Block B, prototype reference)

Standalone PDF → CAE-templated DOCX prototype at `scripts/test_docx_conversion.py`. **Verdict (2026-04-14): go on the Claude path (`--mode claude`).** The fast/hybrid backends are still checked in for reference but were superseded by the Claude extractor (Unit 4.5) and are not used by the production pipeline. Unit 5 lifted the Claude-mode rendering helpers into `backend/app/pipelines/docs/converter.py`. The script remains useful for ad-hoc experiments — its cache lives at `docs_example/conversion_prototype/.cache/` and is intentionally separate from the pipeline cache at `state/cache/claude/`. Non-obvious traps from the prototype (still relevant when iterating on the converter):

- **Java 21 required, not on PATH by default.** opendataloader-pdf calls a Java CLI under the hood. On Alex's macOS, Java 21 lives at `/opt/homebrew/opt/openjdk@21` but the system stub at `/usr/bin/java` shadows it. Always export before running:
  ```bash
  export JAVA_HOME=/opt/homebrew/opt/openjdk@21
  export PATH="$JAVA_HOME/bin:$PATH"
  ```
  Without this you get `Unable to locate a Java Runtime`. Worth adding to `~/.zshrc` permanently.

- **Two extraction backends, NEITHER is Claude.** `--mode fast` is the local Java extractor; `--mode hybrid` talks to a local server (`opendataloader-pdf-hybrid --port 5002`) that runs **IBM Docling**, not Claude. opendataloader-pdf 2.2.1 has no Claude integration despite the speculative `test_hybrid_claude` reference test in `backend/tests/test_pdf_extraction.py`. The `hybrid` parameter only accepts `off` or `docling-fast`. If we want a real Claude pass we have to build it ourselves against the Anthropic SDK.

- **fast mode reorders content past images.** fast's JSON walks paragraphs first then images, so an image belonging to AM3394 ends up rendered below AM3030 in the body. Cannot be fixed in the converter — the source ordering is already wrong. Use `--mode hybrid` for any PDF where image-to-paragraph anchoring matters.

- **hybrid mode runs OCR over every embedded screenshot.** Docling extracts UI labels, dialog buttons, form fields, table cells from screenshots and emits them as flat sibling paragraphs. ~110+ noise paragraphs per release note. The converter drops them via spatial overlap: any text element whose bbox center sits inside an image's bbox on the same page is filtered. See `collect_image_bboxes` + `is_inside_image`.

- **hybrid mode does NOT classify page headers/footers.** The CAE corporate band ("Jetsched Communications Release Note", "AIR TRANSPORT INFORMATION SYSTEMS", "SAS CYBERJET …", "Page X sur N") and bare metadata fragments (version triple, MM/YYYY date) get emitted as body paragraphs and have to be filtered by content patterns. See `PAGE_CHROME_PHRASES` / `PAGE_CHROME_RE`.

- **The Cyberjet logo is on every page** (~72×72pt at top-left, y_top ≈ 760) and gets emitted as a body image. Filtered by `is_page_header_logo` (top-of-page position + small bbox). Logo bboxes are EXCLUDED from the OCR-noise filter so we don't accidentally drop real text just below the logo band.

- **Heading levels MUST be pattern-driven, not extractor-driven.** Both backends mis-classify heading levels (fast judges by font size, hybrid by ML layout). The script overrides extractor decisions for known release-notes structures via `classify_release_note_line`:
  - Section names ("Release Features", "Defect Fixes", "Not Tested", …) → `Heading 1`
  - `AM\d{2,5}[:\-]` lines → `Heading 2`
  - "Bug Description:" / "After correction:" / "Steps to reproduce:" → **bold body text**, NOT a heading style. They appear inline under their AM item but DO NOT show in the Word TOC field (only Heading 1/2/3 feed it). See `is_am_subheading` + `add_bold_body_paragraph`.

- **The Word TOC field rebuilds itself, we don't.** The Flightscape template's TOC is an OOXML complex field with cached entries pointing at the original example chapters. We mark its begin `<w:fldChar>` `w:dirty="1"` (`mark_toc_dirty`) and Word offers to update fields when the document is opened. Or right-click → Update Field → Update entire table. We do NOT try to programmatically replace TOC entries — that breaks the field's internal `_Toc####` bookmarks.

- **Cover page strategy: clone-and-fill, not placeholder substitution.** The Flightscape template has 33 named styles but NO `{{placeholder}}` markers. Cover-page artwork (paragraphs 0–37) is preserved untouched, including all `<w:drawing>`, `<w:pict>` and `<w:txbxContent>` elements anchored to those paragraphs. Body content (paragraphs 38+) and example tables are stripped. Cover-page text-box clutter ("If this is your first time…", "Click this text box and delete it", "Update Customer Name…") is wiped via a `<w:txbxContent>` walk because python-docx hides text boxes from `doc.paragraphs`.

- **Cover-page text run substitution is exact-match only.** The text runs we replace ("Sample Product Name", "Version #", "Date", "Customer", "External Business Document") are matched literally against `<w:t>` element contents. If the template ever changes those literals, the cover-page metadata will silently revert to the template defaults — verify by inspection after any template update.

- **Output cache lives outside git.** `docs_example/conversion_prototype/.cache/{fast,hybrid}/<stem>.json` + `<stem>_images/` are reused on subsequent runs unless `--no-cache` is passed. The whole `docs_example/` tree is gitignored. The script also drops `<output>.md` next to `<output>.docx` so reviewers can see the raw extractor markdown.

- **Test data reality.** Only V8.1 PDFs exist locally (`patches/ACARS_V8_1/{8.1.11.0,8.1.11.2,8.1.12.0,8.1.12.1,8.1.12.2}/release_notes/`). V7.3 / V8.0 family-difference checks deferred. The 5 V8.0 PDFs in `docs_example/pdf_examples/8.0/` already have pre-extracted fast-mode JSON in `extracted/fast/` — usable via `--json <path>` to exercise the converter without re-running Java.

- **Hybrid server is heavy.** `opendataloader-pdf-hybrid --port 5002` initializes IBM Docling models in ~30s and uses ~1.5 GB RAM. Use `--device mps` on Apple Silicon. Once started, leave it running for the duration of the iteration session. The script auto-detects whether the server is up via a TCP probe and falls back to fast with a clear log line if not.

Run `python scripts/test_docx_conversion.py --pdf <pdf> --output <docx> --mode hybrid --verbose` for one PDF. See the script docstring for full CLI usage.

---

## Docs Pipeline Wiring Gotchas (Unit 5)

Unit 5 ships the converter in two stages, not one. The orchestrator's `run_scan_product` now does five sequential passes instead of three:

1. SFTP discovery
2. Binaries download
3. Zendesk fetch (`fetch_release_notes`)
4. **Claude extract (`extract_release_notes`)** — new
5. **DOCX render (`render_release_notes`)** — new

Workflow status flow on the docs side: `not_started → downloaded → extracted → converted → ...`. A few non-obvious things to know:

- **`discovered` is gone, replaced by `extracted`.** The old `not_started → discovered → downloaded` two-step inside the fetcher was a sub-step smell (encoded "halfway through the fetch attempt" as a workflow value). It was collapsed in Unit 5: the fetcher now sets `source_url`, `source_pdf_path`, and `status = "downloaded"` together at the success path. `discovered_at` was dropped from `ReleaseNotesState` — Pydantic silently ignores it on load, so existing state files are forward-compatible. **Binaries kept its `discovered` state** because there it's a real first-class state set by SFTP discovery before any download attempt.

- **The four-bullet rule for adding a workflow status value** (so future units don't reintroduce sub-step smells): a value earns its place only if all four are true — (1) retry independence saves real cost or time, (2) failure modes are distinct from neighbors, (3) operators want to filter on it as a real business question, (4) it produces a persisted artifact downstream stages consume. `extracted` passes all four. `discovered` (release notes) passed none. `pdf_exported` (planned for Unit 10) currently fails the rule too — **don't add it when Unit 10 ships**, fold it into the publish action and rely on `last_run.step` for triage.

- **Two cache directories, not one.** The standalone script writes to `docs_example/conversion_prototype/.cache/claude/` and the pipeline writes to `state/cache/claude/`. Both use the same SHA256-keyed format and Pydantic schema, so you can copy a cache file between them when bootstrapping. Keep them separate so script experiments don't pollute prod state.

- **Cache hit means the API is never called, even with `claude.enabled=true`.** SHA256 of PDF bytes is the cache key. Same PDF → same hash → same cached extraction. Different PDF → different hash → fresh API call. The cache loader also checks `extractor_version` so bumping `EXTRACTOR_VERSION` invalidates every cached record automatically.

- **`claude.enabled` gates API calls only, not the convert pass.** The pass always runs. Cache hit → `extracted` for free. Cache miss + `enabled=false` → clean skip with `convert.extract.skipped reason=claude_disabled`, workflow status untouched, `last_run.state=success`. Cache miss + `enabled=true` → real API call. Dev mode gets the full pipeline including DOCX rendering on cached patches without paying anything.

- **`extract_release_notes` returns a literal, not just None.** `"extracted"` on success, `"skipped_no_api"` on cache miss + disabled API. The orchestrator uses a `result_holder = {"value": None}` closure to capture the return value through `run_cell` (which wraps the work function). The literal lets us count `notes_extract_skipped` separately from `notes_extracted` without inventing a new workflow status.

- **`source_pdf_path` should always be absolute.** The fetcher writes absolute paths via `settings.patches_dir / product_id / version / "release_notes" / safe_name(...)`. The converter uses `Path.resolve()` on the value, so a *relative* path would resolve against the current working directory (which is `backend/` when running from there) instead of the project root. **If you ever hand-edit a state file**, use absolute paths or the smoke test will fail with `Source PDF missing`.

- **Two passes, not one mixed pass.** Pass 4 walks every `downloaded` patch and runs extract; Pass 5 walks every `extracted` patch and runs render. This is the standard ETL stage pattern (Airflow tasks, Dagster ops, Prefect tasks) and gives clean per-stage logs (`scan.docs.extract.*` vs `scan.docs.render.*`) and per-stage retry semantics. The cache makes "fix-and-retry render" cost zero API dollars.

- **Step name semantics, post-Unit-5.** `cell.last_run.step` is non-None only when `state == "failed"`. The lifecycle helper sets `step = step_name` (the outer name passed to `run_cell`) on exception. Today's full step set: `download` (binaries Pass 2), `fetch_release_notes` (Pass 3), `extract` (Pass 4), `render` (Pass 5). One step per pass, no mid-flight updates.

- **`not_found_reason` side field.** When the fetcher catches `ZendeskNotFound` it sets `cell.not_found_reason = "no_match"`; for `ZendeskAmbiguous` it sets `"ambiguous_match"`. This is a side field on `ReleaseNotesState` (not a status split) so the future UI can render different copy ("no article yet" vs "multiple matches — please review on Zendesk") without bloating the workflow `Literal`. Unit 8 will read it.

- **Smoke test recipe** (no API call, real end-to-end):
  1. Copy a PDF + its images dir into `patches/<product>/<version>/release_notes/`
  2. Copy the matching cached extraction from `docs_example/conversion_prototype/.cache/claude/<hash>.json` to `state/cache/claude/<hash>.json` (the hash filename matches because both keys are SHA256 of the PDF bytes)
  3. Add a patch entry to `state/patches/<product>.json` with `release_notes.status = "downloaded"` and an **absolute** `source_pdf_path`
  4. Call `run_scan_product(...)` directly (or `POST /pipeline/scan` via the API) — Pass 4 hits the cache, Pass 5 renders the DOCX. Total cost: $0.

- **Tests structure.** `backend/tests/test_docs_extract.py` covers `extract_release_notes` in isolation (cache hit, skip, failure, version guard). `backend/tests/test_docs_render.py` covers `render_release_notes` in isolation against the real Flightscape template. `backend/tests/test_orchestrator_docs_pass.py` was extended with `_build_claude_client` tests and a `TestExtractRenderPasses` class covering the multi-scan retry scenarios. The existing Unit 3 fetcher tests were updated to drop the `discovered` intermediate state and add `not_found_reason` assertions.

---

## Scan History + Refetch Gotchas (Unit 6)

Unit 6 adds durable scan history and two refetch endpoints. The machinery is small but a few things are easy to mis-reason about:

- **Two kinds of scan — different concurrency rules.** `is_main_scan_running()` only considers records whose trigger is in `{"cron", "manual"}`. A `targeted` or `bulk_docs` record with `finished_at: null` does NOT return True. This is deliberate: main scans are mutually exclusive (two of them would stomp each other's state writes), but targeted/bulk refetches ride on the per-cell lock (`last_run.state == "running"`) which is fine-grained enough that a main scan and a refetch can coexist without double-working any cell. If you change this, re-read PLAN_DOCS_PIPELINE.md §4.1 before committing.

- **FastAPI route order matters for `/pipeline/scan/release-notes`.** The bulk refetch endpoint must be declared before `/pipeline/scan/{product_id}` or FastAPI happily routes `"release-notes"` into the `{product_id}` path param and returns 404 ("Product release-notes not found"). There's a comment on the endpoint pinning this so future edits don't silently break it.

- **`refetch_release_notes` saves after EACH pass, not just at the end.** If the process dies mid-refetch (SIGKILL, crash), the tracker reflects the last successful pass. That matters because a refetch is three sequential passes (fetch → extract → render) and the render pass can take seconds to minutes. Matches the "partial success is visible" principle from the main scan.

- **Refetch returns `outcome`, the endpoint decides the HTTP status.** The orchestrator helper is HTTP-agnostic — it returns `{outcome: "converted"|"downloaded"|"not_found"|"extract_skipped"|"not_eligible"|"already_running"|"failed", ...}`. The endpoint layer maps: `not_eligible → 409`, `patch not found → 404`, everything else → 200 (including `failed` and `already_running`). This keeps the helper reusable from the bulk loop and any future webhook entry point without HTTP leaking into it.

- **Stale in-flight records block forever.** If the backend crashes mid-scan, the scan record stays with `finished_at: null` and every subsequent `POST /pipeline/scan` returns 409. Recovery today is manual: delete the stale file from `state/scans/`. A proper watchdog (pid check, or ignore-if-older-than-1-hour) is a v2 concern. When it bites you, `ls -lt state/scans/ | head` and remove anything that's hours old with `finished_at: null`.

- **Counters on the ScanRecord use the exact orchestrator counter names.** `_aggregate_counts()` sums 11 keys from the per-product dicts (`new_patches`, `downloaded`, `failed`, `notes_downloaded`, `notes_not_found`, `notes_failed`, `notes_extracted`, `notes_extract_skipped`, `notes_extract_failed`, `notes_rendered`, `notes_render_failed`) plus a derived `product_errors`. Adding a new counter to `run_scan_product()` means also adding it to `_SCAN_COUNTER_KEYS` in `api/pipeline.py`, otherwise it silently drops out of scan history.

- **`scans_dir=` kwarg on every helper, same as `load_tracker(state_dir=...)`.** Needed so tests can isolate via `tmp_path` without monkeypatching `settings.scans_dir` (which is a `@property` and not straightforward to patch). Production code calls them without the kwarg, which defaults to `settings.scans_dir = state/scans/`. Follow this pattern when adding new helpers that touch filesystem state.

- **Targeted refetch with `docs.enabled=false` returns `outcome="failed", error="zendesk_unavailable"`, NOT 500.** The helper detects the missing Zendesk client up front and short-circuits with a clean response. The endpoint still writes a scan record so there's an audit trail. Only genuine exceptions (network, auth, parsing) bubble up to the lifecycle helper as `last_run.state=failed`.

- **Smoke test recipe (no external APIs):** start the server with `docs.enabled=false`, curl the endpoints, inspect `state/scans/`. The 409 guard, route registration, scan-record persistence, finalization-on-exception, eligibility checks (200/404/409), bulk version-prefix filter, and the locking asymmetry all exercise without calling Zendesk / Claude / Jira. Details in the 2026-04-17 smoke test log in [PLAN_DOCS_PIPELINE.md Unit 6](PLAN_DOCS_PIPELINE.md).

---

## Logging convention

Every backend log line in the pipeline follows one convention so `grep` works everywhere and later units (Zendesk fetcher, converter, scan history) stay consistent with the binaries code.

- **Event naming:** `subsystem.action.outcome`. Examples: `binaries.download.start`, `binaries.download.success`, `binaries.download.failed`, `scan.product.start`, `scan.product.summary`, `scan.summary`.
- **Payload style:** inline `key=value` pairs in the log message, formatted via `%s` placeholders. Greppable with plain `grep "version=8.1.16.1"` across every layer. Example:
  ```python
  logger.info(
      "binaries.download.success product=%s version=%s files=%d",
      product_id, version, count,
  )
  ```
- **Standard fields:** `product`, `version` on every pipeline log line. `step` is optional — use it only when a pipeline has named sub-phases (e.g. Zendesk fetch has `login`, `find_article`, `download_pdf`). Binaries has one phase, so `step` is omitted there.
- **Exceptions:** always use `exc_info=True` so the traceback lands in the rotating file logger. The one-line event message still follows the `subsystem.action.failed` convention.
- **Summary lines:** every pass (binaries, docs fetch, converter) emits a per-patch outcome line *and* a per-pass summary line with counts — `scan.product.summary product=… discovered=%d downloaded=%d failed=%d` and a final `scan.summary` aggregating across products.

Rule of thumb: a future you grepping logs at 11pm should be able to type `grep "version=X.Y.Z.W"` and see every event across every layer that touched that patch, in order, without having to correlate timestamps.

---

## Mockup → Frontend (historical)

The original mockup gaps (hardcoded data, fake timestamps, non-recomputing description, placeholder buttons) were all addressed during F2–F4. The live frontend reads from the API, uses real per-pipeline timestamps, recomputes the Jira description via `useEffect`, and wires real handlers. See [COMPLETED_PLAN_FRONTEND.md](COMPLETED_PLAN_FRONTEND.md) for the original plan and the F4 design notes below for what was actually built.

---

## Backend — COMPLETE

All 5 backend blocks are done. 121 tests passing. All 10 API endpoints live at `localhost:8000` (Swagger at `/docs`).

| Block | What | Tests | Status |
|-------|------|-------|--------|
| 1 | Scaffold + Config + State + Models | 17 | **DONE** |
| 2 | SFTP Integration (connector + scanner + parsers) | 38 | **DONE** |
| 3 | Jira Integration (client + ticket builder + attachment) | 28 | **DONE** |
| 4 | Services + Pipeline Stubs (orchestrator + patch_service) | 16 | **DONE** |
| 5 | FastAPI App + API Endpoints (10 endpoints + error handling) | 22 | **DONE** |

**Verify:**
```bash
cd backend && pytest tests/ -v -k "not integration"   # 121 tests
cd backend && uvicorn app.main:app --reload            # API on :8000
```

---

## Frontend Build Blocks

The frontend is React + Vite + Tailwind. All components and styles are extracted from `product-control-center-mockup.jsx`. Full details in `PLAN_FRONTEND.md`.

**Source material:**
- `product-control-center-mockup.jsx` — visual design, component structure, theme tokens, Jira modal fields
- `FRONTEND_WORKFLOWS.md` — API response shapes, rendering rules, UI mockups
- `config/pipeline.json` — field options (client, environment, release type)

### Block F1: Scaffold + Shared Code (small) ✅

Vite scaffold, install deps, configure proxy, extract shared constants/types/API client from mockup.

**Files to create:**
```
frontend/
├── vite.config.ts              # Dev proxy /api → :8000
├── src/
│   └── lib/
│       ├── constants.ts        # dk theme tokens, STATUS_CONFIG, FIELD_OPTIONS, input styles
│       ├── types.ts            # TypeScript types from FRONTEND_WORKFLOWS.md
│       └── api.ts              # Typed fetch wrapper + ApiError class
```

### Block F2: Layout + Dashboard (medium) ✅

App shell with sidebar + react-router-dom view switching, dashboard with summary cards, product cards, and actionable table.

**Files created:**
```
frontend/src/
├── App.tsx                     # BrowserRouter + Routes (/ and /pipeline)
├── views/
│   └── Dashboard.tsx           # Summary cards, product cards, quick actionable table
└── components/
    ├── layout/
    │   ├── Sidebar.tsx         # NavLink nav (mockup lines 558–619)
    │   ├── Header.tsx          # Scan button + last scan time
    │   └── AppLayout.tsx       # Shell: Sidebar + Header + Outlet, scan mutation
    └── shared/
        ├── StatusBadge.tsx     # Status dot + label (mockup lines 79–88)
        ├── SummaryCard.tsx     # Stat card (mockup lines 918–924)
        ├── Th.tsx              # Table header cell
        └── Td.tsx              # Table data cell
```

### Block F3: Pipeline View (medium) ✅

Main working view with filter bar, actionable patch table, collapsible history section.

**Files created/modified:**
```
frontend/src/
├── views/
│   └── Pipeline.tsx            # Filter bar + actionable/history tables
├── components/
│   └── shared/
│       └── Td.tsx              # Added `small` prop
└── App.tsx                     # Replaced placeholder with Pipeline import
```

**Design decisions:**
- No separate `PatchTable.tsx` — actionable and history tables have different column structures, kept inline in `Pipeline.tsx`
- Action buttons show 3 states: active (pending_approval), greyed out/disabled (before pending), hidden (published)
- Product filter reads URL param from Dashboard navigation (`?product=...`)
- Product column commented out (single product for now, ready to re-enable)

### Block F4: Modals + Actions (large) ✅

Patch detail timeline and Jira approval modal with full editable form.

**Files created/modified:**
```
frontend/src/
├── components/
│   └── patches/
│       ├── PatchDetailModal.tsx    # Timeline view (mockup lines 402–506)
│       └── JiraApprovalModal.tsx   # Full Jira form (mockup lines 141–363)
├── views/
│   ├── Pipeline.tsx               # Wired modals, status badges open detail, URL params
│   └── Dashboard.tsx              # Wired buttons → navigate to Pipeline with modal params
```

**Design decisions:**
- Status badges in actionable table are clickable → opens PatchDetailModal (replaced Eye icon)
- Dashboard approve/detail buttons navigate to `/pipeline?approve=...` or `?detail=...`
- Pipeline reads URL params on load to auto-open the right modal
- Approve buttons shown disabled/greyed when pipeline not ready (not hidden)
- Detail modal: two-column flex layout with bottom-aligned buttons
- Description auto-recomputes via useEffect when releaseName/createUpdate changes (fixes HANDOFF issue #3)
- **Jira API calls currently de-wired** — submit shows toast with payload for 5s (dry-run mode), ready to re-wire

### Block F5: Polish (small) ✅

Loading skeletons, error toasts, empty states, sidebar animation fix.

**Files created/modified:**
```
frontend/src/
├── main.tsx                        # Global React Query error → styled persistent toast
├── components/
│   ├── layout/
│   │   └── Sidebar.tsx             # Smooth opacity fade on collapse/expand
│   └── patches/
│       └── PatchDetailModal.tsx    # Inline error state for failed detail fetch
└── views/
    ├── Dashboard.tsx               # Realistic loading skeletons (cards + table)
    └── Pipeline.tsx                # Realistic loading skeletons (filter bar + table)
```

**Design decisions:**
- No inline error banners — all API errors show as persistent red toasts (global handler in main.tsx) with status code, endpoint, and error detail
- Sidebar text fade uses CSS opacity transition + overflow-hidden instead of conditional rendering, so collapse and expand both animate smoothly
- PatchDetailModal has its own inline error since it's a modal (toast alone isn't enough context)
- Jira approval modal stays in dry-run mode (deferred to separate block)

### Block F6: Testing (medium) — DEFERRED

Frontend testing deferred — backend tests (121 passing) + logging provide sufficient coverage for MVP. Full plan saved in `PLAN_FRONTEND_TESTING.md` for when frontend tests are needed (Vitest + RTL for components, Playwright for E2E).

---

## Block Summary

| Block | What | Size | Depends on | Status |
|-------|------|------|------------|--------|
| F1 | Scaffold + Shared Code | Small | Backend complete | ✅ Done |
| F2 | Layout + Dashboard | Medium | F1 | ✅ Done |
| F3 | Pipeline View | Medium | F2 | ✅ Done |
| F4 | Modals + Actions | Large | F3 | ✅ Done |
| F5 | Polish | Small | F4 | ✅ Done |
| F6 | Testing | Medium | F5 | Deferred |

### Git flow per block

```
1. Agent implements block
2. Run: cd frontend && npm test (from F6 onward)
3. Manual check in browser
4. git commit + git push
```

### After all frontend blocks

```bash
cd frontend && npm run build               # build static files
cd backend && uvicorn app.main:app         # serves everything on :8000
# Full flow: dashboard → scan → approve → published
```
