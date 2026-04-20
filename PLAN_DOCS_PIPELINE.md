# Docs Pipeline — Plan

Status: **design / brainstorm**. No code yet. This document captures the design for the release-notes (docs) side of the pipeline so we can build it in clean blocks without re-deciding things mid-flight.

---

## 1. Scope and guiding principles

The docs pipeline turns a published Zendesk release-note PDF into a CAE-templated DOCX, attaches it to the same patch entry as the binaries, and runs it through its own approval + Jira flow.

**Guiding principles**

1. **Binaries on SFTP are the single source of truth.** A patch exists because SFTP says so. Release notes are an *attribute* of an existing patch — never the other way around. If Zendesk has notes for a version we've never seen on SFTP, we ignore it (log a warning).
2. **Two independent tracks per patch.** `binaries` and `release_notes` are already separate sub-objects in the state model with their own status, their own approval, and their own Jira ticket. The docs pipeline plugs into the existing `release_notes` slot — no schema split.
3. **Idempotent state machine.** "Retry" is not a separate concept — it's just running the discovery step again on a patch whose status is in a retry-eligible state. Same code path as the first try.
4. **No new infrastructure.** Same JSON state files, same orchestrator pattern, same approval endpoint shape as binaries.

---

## 2. The three blocks

The work splits cleanly into three blocks. They depend on each other in order, but block A and block B can be prototyped in parallel against fixtures.

### Block A — Release-notes discovery + download (Zendesk)

**Goal:** given a patch like `8.1.16.1`, find the matching release-note PDF on Zendesk and download it locally.

**Inputs:** patch version string, product family.

**Outputs:**
- A PDF saved under `patches/<product>/<version>/release_notes/<filename>.pdf`.
- State transition on `release_notes`: `not_started → downloaded` (single transition — set `source_url`, `source_pdf_path`, and status together at the success path; collapsed from the original `not_started → discovered → downloaded` in Unit 5).
- New fields on `ReleaseNotesState`: `source_pdf_path`, `source_url`.

**Naming convention to test (Alex confirmed this is standard):**
- File: `8.0.16.1 - Release Notes.pdf`
- Category: `8.0.16` — opening the category lists all `8.0.16.x` patches.

**Matching logic:**
1. Resolve category by `<major>.<minor>.<maintenance>` (e.g. `8.1.16`).
2. Within the category, look for an article whose title or attachment filename starts with the full patch version (`8.1.16.1`).
3. Download the first PDF attachment matching the pattern.

**Already-built reference:** [scripts/test_zendesk_scraper.py](scripts/test_zendesk_scraper.py) — proves curl_cffi + legacy `/access/login` works around Cloudflare. Code lifts cleanly into `backend/app/integrations/zendesk.py`.

**Failure modes** (how each maps to the two state machines — see section 3):

- **Article doesn't exist yet** (notes published late) → **workflow status** `not_found`, **run status** `success`. Not a failure, just a clean negative result. **Not auto-retried** by future main scans — recovery is via the manual "Refetch Release Notes" button or a future email webhook (see section 4.0 for why).
- **Login or scraping breaks** (Cloudflare, expired creds, network blip, broken HTML) → **workflow status untouched** (stays whatever it was before the attempt), **run status** `failed` with `step` and `error` populated. Full traceback also logged. Since workflow status didn't change, the next main scan will retry only if the patch was still in `not_started` (i.e. the failure happened on its very first attempt). Otherwise recovery is manual.
- **Found multiple matches** → **workflow status** `not_found` (don't guess, don't pick one). **Run status** `success` (the attempt itself completed fine). Distinct log event `zendesk.fetch.ambiguous_match` instead of `zendesk.fetch.no_match` so it's greppable. Only introduce a dedicated workflow state if ambiguous matches become recurring in practice.

**The principle:** workflow status describes the patch's place in the business process; run status describes what happened on the last attempt. Exceptions modify run status, never workflow status. See section 3.

---

### Block B — DOCX template injection (PDF → CAE DOCX)

**Goal:** take the downloaded source PDF and produce a CAE-templated DOCX ready for review.

**Inputs:** path to source PDF, path to CAE template.

**Outputs:**
- DOCX saved under `patches/<product>/<version>/release_notes/<filename>.docx`.
- State transition: `downloaded → converted`.
- New fields on `ReleaseNotesState`: `generated_docx_path`, `template_version`.

**Lives at:** `backend/app/pipelines/docs/converter.py` — replaces the current stub.

**Risk:** this is the highest-risk block. Plumbing is easy; conversion fidelity is the unknown. Worth prototyping standalone (same way the Zendesk scraper was) before wiring into the pipeline. Questions to answer in the prototype, **not** here:
- Does the PDF have stable structure (headings, tables) we can extract, or is it a flat layout?
- Does the CAE template need section markers / placeholders, or is it just styling?
- What's the fallback when extraction is partial — empty section, or fail the conversion?

**Re-conversion:** if the template is updated, we need a way to re-run conversion on every `pending_approval` doc without re-downloading the PDF. Same idempotency principle — re-running the converter step on a `converted` or `pending_approval` patch should be safe and overwrite the DOCX.

---

### Block C — Merge into the existing approval flow

**Goal:** make the docs track behave like the binaries track in the orchestrator, the API, and the UI — while keeping their approvals fully independent.

> **Block C is a category, not a unit of work.** It covers orchestrator, API, UI, and approval semantics. Each of those is broken down into a separate PR-sized unit in [§7](#7-build-plan--prs). This sub-section keeps the design intent only; for *what gets built and in what order*, see §7 — that's the source of truth.

**Design intent (the parts that aren't mechanical):**
- The existing `approve` endpoint stays one endpoint. Same contract, request body targets `binaries` *or* `release_notes`.
- A main scan is the five-pass flow from §4.0 (SFTP / binaries / docs fetch / docs extract / docs render). The docs fetch pass auto-acts on `not_started` only — never `not_found` (see §4.2 for the asymmetry).
- The existing [Pipeline.tsx](frontend/src/views/Pipeline.tsx) table is already structured right: one row per patch, two status-badge columns, two approval buttons. **All UI changes are additive** — workflow status badges stay exactly as they are. Filter bar, history table, approval modal, overall layout: unchanged.
- Approving binaries and approving docs are still independent buttons / endpoints / Jira tickets. The docs side has one extra final step: after approval, convert the approved DOCX to PDF and attach *that* to the docs Jira ticket. State: single `approved → published` transition (no intermediate `pdf_exported` — see Unit 10).

---

## 3. State model — two orthogonal state machines per track

This is the central design decision. Every track on every patch (binaries and release_notes) has **two independent state machines** that answer different questions and have different lifetimes:

| | **Workflow status** | **Run status** |
|---|---|---|
| **Question** | "Where is this track in the business process?" | "What did the latest attempt do?" |
| **Lifetime** | Lives for the life of the patch (days / weeks) | Lives for one attempt (seconds / minutes) |
| **Changed by** | Business events (discovered, downloaded, approved, published) | The execution engine (started, succeeded, failed) |
| **Resets?** | Never (monotonic; explicit rollback would be a future feature) | Every new attempt overwrites it |
| **`failed` as a value?** | **Never.** Errors don't belong in a workflow state machine. | **Yes, naturally** — it describes the attempt, not the patch. |

This is the standard pattern in every production system that runs long-lived objects through repeated attempts: GitHub Actions (PR vs workflow run), Airflow (DAG vs task instance), Stripe (payment intent vs charge attempt), Kubernetes (Deployment vs Pod). Run-state failures don't corrupt workflow state.

### 3.1 Workflow status

**`BinariesState.status`** (unchanged from today):
```
discovered → downloaded → pending_approval → approved → published
```

**`ReleaseNotesState.status`** (as of Unit 5 + Unit 10 planned):
```
not_started ─┬─ downloaded → extracted → converted → pending_approval → approved → published
             │
             └─ not_found  ◀── Zendesk lookup ran cleanly, no matching article yet
```

`not_found` is a clean-negative branch. It means "we looked, Zendesk doesn't have it yet" — a soft, expected outcome since notes are often published after the binaries land on SFTP. Re-entered from `not_started` and exited back to `downloaded` on a future successful scan (triggered by manual refetch or future webhook, never auto-scan — see §4.2). The side field `not_found_reason` distinguishes `"no_match"` from `"ambiguous_match"`.

**Historical:** earlier drafts had a `discovered` workflow state between `not_started` and `downloaded`, and a `pdf_exported` state between `approved` and `published`. Both were collapsed — they were sub-steps of single business actions, not real business stages. The four-bullet rule (§3.5) is the test we apply to every proposed new workflow status value.

**Workflow status contains no error values.** Ever. Errors are described by run status.

### 3.2 Run status

A new sub-object `last_run` attached to *both* `BinariesState` and `ReleaseNotesState`:

```python
class LastRun(BaseModel):
    state: Literal["idle", "running", "success", "failed"] = "idle"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    step: str | None = None         # free-form, e.g. "zendesk_login", "pdf_download"
    error: str | None = None        # one-line error summary for triage
```

- `idle` — never been attempted (initial value)
- `running` — an attempt is in progress right now. Also acts as the per-cell lock: any other trigger seeing `running` skips.
- `success` — last attempt completed without exception (regardless of whether it found/changed anything)
- `failed` — last attempt raised an exception. `step` and `error` are populated. **Can happen at any step for any reason** — the two fields tell you which.

**`step` is free-form string.** Same value is also emitted in the log line, so there's one source of truth. Free-form means adding a new step tomorrow doesn't require a migration.

### 3.3 Putting both state machines together

Updated Pydantic models:

```python
class LastRun(BaseModel):
    state: Literal["idle", "running", "success", "failed"] = "idle"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    step: str | None = None
    error: str | None = None


class BinariesState(BaseModel):
    status: Literal["discovered", "downloaded", "pending_approval",
                    "approved", "published"] = "discovered"
    last_run: LastRun = LastRun()
    # + existing timestamps, jira fields


class ReleaseNotesState(BaseModel):
    # Post Unit 5 (added "extracted", dropped "discovered") + Unit 10 planning (no "pdf_exported")
    status: Literal["not_started", "downloaded", "extracted", "converted",
                    "pending_approval", "approved", "published",
                    "not_found"] = "not_started"
    last_run: LastRun = LastRun()
    not_found_reason: Literal["no_match", "ambiguous_match"] | None = None
    # + existing timestamps, jira fields, source_pdf_path, record_json_path, generated_docx_path
```

A patch discovered from a scan produces **four independent cells**:
- `patch.binaries.status` (workflow) + `patch.binaries.last_run` (run)
- `patch.release_notes.status` (workflow) + `patch.release_notes.last_run` (run)

All four progress independently. Binaries can be `approved` while docs are `not_found`, and at the same moment binaries can have `last_run.state = success` while docs have `last_run.state = failed`. That's not a contradiction — it's the whole point.

### 3.4 State transitions during an attempt

The lifecycle of every attempt (binaries or docs) is the same five steps:

1. **Pre-flight check:** if `last_run.state == running`, skip this attempt (another worker is already on it).
2. **Start:** set `last_run.state = running`, `last_run.started_at = now()`, clear `step` and `error`.
3. **Execute:** do the work, updating `last_run.step` as the attempt progresses through named steps.
4. **On success:**
   - Set `last_run.state = success`, `last_run.finished_at = now()`.
   - Advance `status` (workflow) if appropriate — e.g. docs fetch `not_started → downloaded`, or `not_started → not_found` on clean negative.
5. **On exception:**
   - Set `last_run.state = failed`, `last_run.finished_at = now()`, populate `last_run.step` and `last_run.error`.
   - **Do not touch `status`** (workflow) — it stays whatever it was before the attempt.
   - Emit a full structured log line with traceback.

Next attempt starts from step 1. When it begins, `last_run.state` flips back to `running` and the previous failure is naturally overwritten. No manual "clear error" button needed — success self-heals.

### 3.5 Why this two-machine model is the right call

**Why workflow status has no `failed`:**
- Workflow status describes *the patch's place in the business process*. A failed attempt doesn't move the patch backward in the process — it just means "the last attempt didn't complete". Encoding that as a workflow state would conflate "business stage" with "execution outcome".
- Status fields that try to encode debugging info age badly: they drift from logs, and you end up with two sources of truth for the same information.
- The UI needs to filter by business stage ("show me all `pending_approval` patches") without those filters being polluted by attempt outcomes.

**Why run status earns its place as a separate machine:**
- It gives the UI a direct signal for "this cell is currently working" (spinner) and "this cell's last attempt broke" (red dot + tooltip) without polluting workflow status.
- `step` and `error` give Alex enough triage info to decide "retry, investigate, or ignore" without opening a log file for 80% of cases. The other 20% still grep logs — the two systems cooperate, not compete.
- `last_run.state == running` is a natural per-cell lock without needing a separate lock table.
- It resets cleanly on every attempt, which matches how execution engines think about work.

**Why this maps to industry patterns:**
- GitHub Actions: PR has workflow state, each run has `queued/in_progress/success/failure`. A failed run doesn't mark the PR as errored.
- Airflow / Dagster / Prefect: DAG has definition, task instances have `scheduled/running/success/failed/up_for_retry`.
- Stripe: payment intent has lifecycle, each charge attempt has its own outcome.
- Every serious long-running job system works this way. Future contributors will recognize it immediately.

---

## 4. Scans and retriggers

### 4.0 Main scan flow

A main scan is **five sequential passes over the same state** (after Unit 5), each independent. SFTP discovery writes new patches to state *before* any download happens — the moment a patch is discovered, it exists in the system as a tracked entity, with `binaries.status = discovered` and `release_notes.status = not_started`. From that moment on, the two tracks progress independently.

```
POST /pipeline/scan (main scan):

  1. SFTP DISCOVERY
     ─ list SFTP, find new patches
     ─ write to state immediately:
         binaries.status      = discovered
         release_notes.status = not_started

  2. BINARIES PASS — for each cell where binaries.status == discovered
                     AND last_run.state != "running":
     ─ run the per-cell lifecycle (section 3.4)
     ─ on success: binaries.status moves discovered → downloaded → pending_approval
     ─ on failure: binaries.last_run.state = failed, workflow status untouched

  3. DOCS FETCH PASS — for each cell where release_notes.status == not_started
                       AND last_run.state != "running":
     ─ fetch article + PDF from Zendesk
     ─ if found:        status moves not_started → downloaded (single transition)
     ─ if no article:   status = not_found, not_found_reason = "no_match"
     ─ if ambiguous:    status = not_found, not_found_reason = "ambiguous_match"
     ─ if exception:    run state = failed, workflow status untouched

  4. DOCS EXTRACT PASS — for each cell where release_notes.status == downloaded
                         AND last_run.state != "running":
     ─ SHA256-keyed cache lookup on the PDF bytes
     ─ cache hit:                            status = extracted (free, no API)
     ─ cache miss + claude.enabled=true:     call Claude API, save cache,
                                             status = extracted
     ─ cache miss + claude.enabled=false:    clean skip (workflow status
                                             untouched, run state success,
                                             log convert.extract.skipped)
     ─ if exception:                         run state = failed, status untouched

  5. DOCS RENDER PASS — for each cell where release_notes.status == extracted
                        AND last_run.state != "running":
     ─ load persisted record JSON + Flightscape template
     ─ render via python-docx
     ─ on success: status moves extracted → converted
     ─ on failure: run state = failed (retry on next scan reuses cache — free)

  6. Persist scan record to state/scans/<scan_id>.json with counts per pass.
```

**Critical: the docs pass auto-acts on `not_started` only, NEVER on `not_found`.**

This is the most important rule in the docs pipeline and it's worth being loud about.

The naive approach would be to also auto-retry `not_found` patches on every scan ("maybe the notes are published now"). That's the **trap**: every cron tick would re-hit Zendesk for every patch still missing notes, and the eligibility set grows monotonically as the backlog accumulates. One misconfigured backoff away from getting the scraper IP blocked. Linear-in-backlog load on a third-party Cloudflare-protected site is exactly what you don't want.

Instead: **publishing release notes is the developer's job, not the cron's job to keep guessing.** When notes are published, the recovery mechanism is explicit human (or future automated) action, not blind polling:

- **Today:** Alex sees `not_found` in the UI and clicks the "Refetch Release Notes" action button on that row.
- **Future:** an email webhook (or any other "notes are now available" signal) hits the targeted refetch endpoint. Same code path, no design change.

Auto-fetch acts on patches that have **never been tried** (`not_started`); manual / future-webhook acts on patches that have been tried and came up empty (`not_found`). Two different intent levels, two different trigger mechanisms, one shared per-cell lifecycle.

**Why five sequential passes and not interleaved:**
- A binaries failure in pass 2 does not block any docs pass for the same patch — the two tracks are independent at the cell level.
- Sequential passes keep logs readable and isolate external-system blast radius (SFTP / Zendesk / Claude each have their own pass). Parallelizing later is a small change if scan volume ever demands it.
- Each docs pass has its own retry semantics: Pass 4 retries re-use the cache (no $ cost), Pass 5 retries re-use the persisted record JSON (no API cost). Splitting extract and render into separate workflow stages is the standard ETL pattern (Airflow/Dagster/Prefect) — see Unit 5 decisions 1 and 3 for the four-bullet rule we used.

### 4.1 Two kinds of scan

These are different enough that they get different endpoints, different log namespaces, and different locking rules:

| | **Main scan** | **Targeted docs fetch** |
|---|---|---|
| **Scope** | Walks SFTP, discovers new patches, runs all 5 passes (binaries download + docs fetch + extract + render) for everything new or retry-eligible | One (or N) specific known patch(es). Does not touch SFTP. Runs Pass 3 (+ Pass 4 + 5 if newly `downloaded`). |
| **Trigger** | Cron or "Start scan" button | UI row action or bulk version-header button |
| **Endpoint** | `POST /pipeline/scan` (already shipped in Block 5; Unit 6 adds the 409 guard) | `POST /patches/{product_id}/{patch_id}/release-notes/refetch` (single, Unit 6), `POST /pipeline/scan/release-notes?version=...` (bulk, Unit 6) |
| **Log namespace** | `scan.main.*` | `zendesk.fetch.*` (direct, no `scan.*` wrapping) |
| **Locking** | Rejects if another main scan is running (409 Conflict) | Allowed during a main scan, because the per-cell lock (`last_run.state == running`) prevents double-work on the same cell |
| **Purpose** | Discover + progress everything in one sweep | "I know this specific patch needs its notes — don't make me wait for the next cron tick" |

The targeted fetch reuses the same Zendesk code internally, but it's a different workflow: the main scan discovers new work, the targeted fetch acts on a specific known cell. Don't conflate them.

### 4.2 Retrigger — three layers, one code path

All three layers call the same per-cell attempt function. The state is the queue — there is no separate retry table. The key asymmetry is **what counts as eligible** depending on who's triggering.

| Layer | Trigger | Eligible cells | Purpose |
|-------|---------|----------------|---------|
| **Auto on main scan** | Every `POST /pipeline/scan` (cron or manual) | `release_notes.status == not_started` AND `last_run.state != running` | First-look only. Acts on patches that have never been tried. Bounded by definition — `not_found` is excluded so the eligibility set doesn't grow with the backlog. |
| **Per-row manual** | UI "Refetch Release Notes" action button on a single patch | `release_notes.status ∈ {not_started, not_found}` AND `last_run.state != running` | Alex (or a future webhook) saying "look again now, the developer just published". Explicit human intent — `not_found` is fair game here. |
| **Bulk** | Version-header button or filtered API call (`POST /pipeline/scan/release-notes?version=...`) | same as per-row manual | Same explicit-intent semantics, but for a batch — e.g. "Refetch all missing notes in V8.1" after the developer announced a doc drop. |

**Eligibility check pseudocode:**
```python
def is_eligible(cell, trigger):
    if cell.last_run.state == "running":
        return False  # per-cell lock — another worker is on it
    if trigger == "auto_scan":
        return cell.status == "not_started"
    else:  # manual or bulk
        return cell.status in {"not_started", "not_found"}
```

**Why no backoff window.** Earlier draft had a backoff timer. Removed because the only thing being auto-retried is `not_started` — and a patch can only be `not_started` *before* its first attempt. By definition, there's nothing to back off from. Manual / bulk triggers represent explicit human intent and don't need rate-limiting either (Alex is the rate limiter). Backoff was solving a problem that no longer exists once `not_found` is removed from the auto-retry set.

**Failed-run cells are a separate question.** If a patch's last attempt threw an exception (`last_run.state == failed`) but workflow status is still `not_started`, the next main scan will pick it up automatically (it's still `not_started`, after all). If we ever need to slow that down, we add backoff *only* for cells with `last_run.state == failed` — but that's a v2 concern, not v1.

**Critical:** do not introduce a separate retry table or queue. Workflow status + run status + `last_run` timestamps already encode "what needs retrying" and "when it was last tried". Two sources of truth is how you end up debugging state drift instead of debugging bugs.

### 4.2.1 The future email-webhook trigger

When the team eventually wants automated "notes are now published" signals, they plug into the **same targeted refetch endpoint** the manual button uses. No design change — just a new trigger calling existing code:

```
[email arrives] → [webhook handler parses version] → POST /patches/{id}/release-notes/refetch
                                                       ↑
                                            same endpoint as the UI button
```

This is why the docs pass deliberately doesn't try to be clever about `not_found` polling: the moment there's a real signal (email, Slack, manual click), it goes through the targeted endpoint. The auto-on-scan path stays narrow and safe.

### 4.3 Scan history

We persist a record of every scan to `state/scans.json` (or `state/scans/<scan_id>.json` — TBD, pick whichever serializes cleaner). Each record captures:

```python
class ScanRecord(BaseModel):
    scan_id: str
    trigger: Literal["cron", "manual", "targeted", "bulk_docs"]
    started_at: datetime
    finished_at: datetime | None         # null while in-flight → acts as "is a scan running?" signal
    products: list[str]                  # products covered
    counts: dict[str, int]               # e.g. patches_total, binaries_new, release_notes_found,
                                         #      release_notes_not_found, release_notes_failed
    duration_ms: int | None
```

**Why:**
- `finished_at IS NULL` is the "main scan running" signal for the 409 Conflict check.
- Persisted history lets the UI later show "last 10 scans" and aggregate outcomes without parsing log files.
- Gives a durable audit trail independent of log rotation.

**Not in v1:** no UI for scan history yet. The data is recorded now so the UI can be added later without a migration.

---

## 5. Resolved questions (historical)

All six original open questions have been resolved. Kept here for history — don't re-open these without a new reason.

1. ✅ **Block A — Zendesk title standardization.** RESOLVED during Unit 3: titles are reliably `<version> - Release Notes.pdf` for the versions Alex tracks. Unit 3 shipped with exact-match + ambiguous-match fallback and that's been sufficient in practice.
2. ✅ **Block A — Zendesk auth model.** RESOLVED during Unit 3: service-account credentials in `.env` (`ZENDESK_SUBDOMAIN`, `ZENDESK_EMAIL`, `ZENDESK_PASSWORD`), same pattern as Jira. Alex pastes them himself per the standing rule.
3. ✅ **Block B — PDF → DOCX prototype.** RESOLVED in Unit 4.5 (Claude path): verdict is GO. Fast and hybrid backends were ruled out (reordering, OCR noise). Claude extraction produces a clean structured record that `render_record()` turns into an acceptable DOCX. Unit 5 shipped the integrated version.
4. ✅ **Block C — DOCX preview in browser.** RESOLVED 2026-04-15: Unit 9 renders DOCX → PDF via `libreoffice --headless` for display-only; Alex opens the local DOCX in Word if he wants to tweak it. No in-browser record editor. See Unit 9 scope for the full rationale.
5. ✅ **State — `last_run` migration.** RESOLVED in Unit 1: lazy default on load. Pydantic `LastRun()` default handles existing state files without a migration script. Same approach was used in Unit 5 for the `discovered`/`extracted` schema change, validated in production.
6. ✅ **State — scan history storage.** RESOLVED in Unit 6 scope: `state/scans/<scan_id>.json` (many small files). Rotation-friendly, no need to load full history into memory for the running-check — just list the dir and inspect each file's `finished_at`.

**Current open questions: none.** If new ones arise during implementation, add them here with a date.

---

## 6. Out of scope for this plan

- Rejecting a release note (rollback path). The binaries side doesn't have it either; we'll add both together later.
- Notifications (Slack/email when new notes are found and waiting for approval).
- Diffing two versions of release notes for the same patch (rare; manual for now).
- Anything in `templates/` beyond the single CAE doc template.

---

## 7. Build plan — PRs

The work is split into **11 PR-sized units**. Every unit produces **one PR**, **one git commit**, and **passing tests** (`cd backend && pytest tests/ -v -k "not integration"` for backend; `cd frontend && npm run build` for frontend). Each unit is small enough to brief a single agent on without ambiguity.

**Conventions for every unit:**
- Each unit has a clearly stated **scope**, list of **files**, **tests**, **dependencies**, and **done criteria**.
- An agent picks up one unit at a time, opens a branch, implements it, runs the test command listed, and commits.
- No unit modifies more than its listed files unless a dependency was missed (in which case: stop and update this plan first).
- Logs in every backend unit follow the convention defined in unit 0.

**Dependency graph:**

```
0 ──► 1 ──► 2 ──► 3 ──► 5 ──► 6 ──► 7 ──► 8 ──► 9 ──► 10
                  │     ▲
                  └─────┘
              4 (parallel — gate before 5)
```

Unit 4 (Block B prototype) is the only one that runs **in parallel** with the rest. It gates unit 5 (don't integrate the converter until the prototype proves DOCX fidelity is acceptable).

---

### Unit 0 — Logging convention + binaries logging retrofit + IOError fix

**Effort:** Small.
**Depends on:** nothing.

**Scope.** Establish the logging convention used by every later unit, retrofit existing binaries code to it as a worked example, and fix one swallowed-exception bug along the way. No new features.

**Files:**
- [HANDOFF.md](HANDOFF.md) — add a one-paragraph "Logging convention" section: events use `subsystem.action.outcome` naming, payload uses `key=value` greppable fields, exceptions use `exc_info=True`, document the standard fields (`product`, `version`, `step`).
- [backend/app/services/orchestrator.py](backend/app/services/orchestrator.py) — convert existing log calls to the new convention. Add a per-patch summary line and a per-scan summary line (counts of new / downloaded / failed).
- [backend/app/pipelines/binaries/fetcher.py](backend/app/pipelines/binaries/fetcher.py) — convert log calls; **fix the bug at line 32**: `IOError` is currently swallowed (returns 0, logs an error, but the caller treats it as success). Re-raise instead so the caller's `try/except` actually sees the failure.

**Tests.** Add a unit test that simulates `_download_recursive` raising `IOError` and asserts the orchestrator catches it (today's behavior is the bug — the orchestrator never sees it). Run full backend suite.

**Done criteria:** all 121 existing tests + new test pass; binaries logs in the new format; HANDOFF.md has the convention paragraph.

---

### Unit 1 — State model foundation

**Effort:** Small.
**Depends on:** unit 0.

**Scope.** Add `LastRun` Pydantic model; add `last_run` field to both `BinariesState` and `ReleaseNotesState`; add `not_found` value to `ReleaseNotesState.status` Literal. **No `ScanRecord` yet — that lives in unit 6 where it has somewhere to be exercised.** Migration is **lazy default on load** (Pydantic default value handles existing JSON files automatically).

**Files:**
- [backend/app/state/models.py](backend/app/state/models.py) — add `LastRun`, add `last_run: LastRun = LastRun()` to both states, extend the release notes Literal.

**Tests.**
- Round-trip: load each existing fixture under [state/patches/](state/patches/), confirm it parses with default `last_run` populated, write it back, confirm bytewise (or semantic) round-trip.
- New `not_found` value parses cleanly.
- Default `LastRun()` has `state == "idle"` and all timestamp fields `None`.

**Done criteria:** all existing tests + new model tests pass; existing state JSON files load without modification.

---

### Unit 2 — Lifecycle helper + binaries retrofit

**Effort:** Medium.
**Depends on:** unit 1.

**Scope.** Implement the per-cell 5-step lifecycle from §3.4 as a single helper. Retrofit the existing binaries download to use it. Binaries gain `last_run` tracking automatically — **no new endpoints, no UI changes**. This is the foundation every later pipeline (docs fetch, converter) reuses.

**Files:**
- `backend/app/services/lifecycle.py` (new) — `run_cell(cell, work_fn, *, step_name)` helper. Pre-flight lock check → set `running` + `started_at` → call `work_fn` → on return set `success` + `finished_at`, on exception set `failed` + `finished_at` + `step` + `error` (one-line summary). Returns success/failure indicator.
- [backend/app/services/orchestrator.py](backend/app/services/orchestrator.py) — wrap the existing binaries download call in `run_cell`. Workflow status transitions stay where they are; the helper only manages `last_run`.

**Tests.**
- Successful run → `last_run.state == "success"`, `started_at` and `finished_at` set, no `step`/`error`.
- Failing run (work_fn raises) → `state == "failed"`, `step` and `error` populated.
- Lock case: call `run_cell` on a cell whose `last_run.state` is already `"running"` → returns immediately, doesn't run `work_fn`.

**Done criteria:** existing binaries download tests still pass; new lifecycle tests pass; binaries run records are visible in the JSON state file after a scan.

---

### Unit 3 — Block A: Zendesk fetcher

**Effort:** Medium.
**Depends on:** unit 2.

**Scope.** Extract the standalone Zendesk scraper from [scripts/test_zendesk_scraper.py](scripts/test_zendesk_scraper.py) into `backend/app/integrations/zendesk.py`. Build `backend/app/pipelines/docs/fetcher.py` that takes a patch and uses the integration to look up the matching release-notes article. Wire into the orchestrator as the docs pass (third pass — see §4.0). **Auto-acts on `not_started` only**, never `not_found`. All Zendesk calls go through `run_cell` from unit 2.

**Files:**
- `backend/app/integrations/zendesk.py` (new) — `ZendeskClient` class: login, find article by version, download PDF. No business logic, just integration.
- `backend/app/pipelines/docs/fetcher.py` (new) — `fetch_release_notes(patch)`: calls the client, on success downloads PDF + transitions workflow status `not_started → downloaded` (single transition, after Unit 5 cleanup), on clean-negative transitions to `not_found` with `not_found_reason` set, on exception lets the lifecycle helper record the failure.
- [backend/app/services/orchestrator.py](backend/app/services/orchestrator.py) — add the docs pass after the binaries pass. Behind a config flag (`pipeline.docs.enabled`) so it can be turned off if Zendesk is unstable.
- [backend/app/pipelines/docs/stub.py](backend/app/pipelines/docs/stub.py) — delete (replaced by `fetcher.py`).

**Tests.**
- Fixture-based tests with recorded HTTP responses (no live calls in CI). Cover: login success, article found + PDF downloaded, article not found (clean negative → `not_found`), Cloudflare 403 (exception → `last_run.state == failed`), ambiguous match (multiple candidates → `not_found` + warning log event).
- Orchestrator integration test: run a full main scan against fixture state, confirm binaries pass and docs pass both run, both update their respective `last_run`.

**Done criteria:** main scan finds and downloads at least one real release-note PDF in dev (manual smoke test); fixture tests cover all five failure modes; existing tests still pass.

---

### Unit 4 — Block B prototype (standalone, parallel) — GATE BEFORE UNIT 5 ✅ GO (2026-04-14)

**Effort:** Small–Medium.
**Depends on:** nothing — runs in parallel with units 0–3.
**Status:** ✅ **Verdict: GO on the Claude path (Unit 4.5).** The fast/hybrid backends were ruled out (fast reorders content past images; hybrid OCRs every screenshot and emits page chrome as body paragraphs). Unit 4.5 added a Claude-based extractor that produces clean structured records with correct image ordering and no page-chrome noise. With prompt caching wired correctly (commit `e0af8e6`), re-extracting the same PDF costs $0.22 down from $3.47 fresh. Unit 5 lifted the Claude-mode rendering helpers from the standalone script into the production pipeline.

**Scope.** Standalone PDF → CAE-templated DOCX prototype. **Not wired into the pipeline.** Goal is to answer: *is the conversion fidelity good enough to ship?* If yes, unit 5 wires it in. If no, the docs pipeline becomes a "human edits the DOCX in Word" loop and the rest of the plan changes shape.

**Files:**
- `scripts/test_docx_conversion.py` (new) — takes a PDF path + template path, produces a DOCX. Same standalone-script style as `test_zendesk_scraper.py`.

**Tests.** Manual eyeball with Alex on **3 representative real PDFs** (one per product family if possible — V7.3, V8.0, V8.1). Document the verdict in the PR description: structure preserved? styles applied? sections in the right order? what's broken? what's acceptable?

**Done criteria:** 3 sample DOCX outputs reviewed with Alex; explicit go/no-go decision recorded in the PR. If no-go, the plan §2 Block B and units 5/9/10 need to be redesigned before continuing.

**First-iteration findings (2026-04-11) — fast vs hybrid extraction backends:**

- **Two extraction backends** are now supported via `--mode {fast,hybrid}`. Both route through `opendataloader-pdf`. `fast` is the local Java extractor; `hybrid` talks to a local `opendataloader-pdf-hybrid --port 5002` server that runs IBM Docling under the hood (NOT Claude — `opendataloader-pdf` 2.2.1 has no Claude integration despite the speculative `test_hybrid_claude` reference test in `backend/tests/test_pdf_extraction.py`).
- **Java prerequisite:** opendataloader-pdf needs Java 21. On Alex's macOS the runtime is at `/opt/homebrew/opt/openjdk@21` and isn't on PATH by default — must export `JAVA_HOME=/opt/homebrew/opt/openjdk@21` and `PATH=$JAVA_HOME/bin:$PATH` before running the script.
- **Template strategy validated:** clone-and-fill works. The Flightscape template is a style donor, not a form. The script preserves cover-page artwork (paragraphs 0–37 carry drawings, text boxes, and section breaks) and strips the instructional body (paragraphs 38+) plus all 7 example tables. Cover-page text-box clutter ("If this is your first time…", "Click this text box and delete it", "Update Customer Name…") is wiped via a `<w:txbxContent>` walk that python-docx doesn't expose through `doc.paragraphs`.
- **TOC field is regenerated by Word, not by us.** The template's TOC is an OOXML complex field with cached entries pointing at the original example chapters. We mark the field's begin `<w:fldChar>` `w:dirty="1"` and Word auto-rebuilds it from the actual headings the next time the document is opened (or via right-click → Update Field).
- **Heading hierarchy is pattern-driven, not extractor-driven.** Both extractors mis-classify heading levels (fast judges by font size, hybrid by ML layout). The script overrides extractor decisions for known release-notes structures via `classify_release_note_line`:
  - "Release Features" / "Defect Fixes" / "Not Tested" / etc. → `Heading 1` (these feed the Word TOC's section level)
  - Lines matching `AM\d{2,5}[:\-]` → `Heading 2` (per-item TOC entries)
  - "Bug Description:" / "After correction:" / "Steps to reproduce:" / etc. → **bold body text**, NOT a heading style, so they appear inline under the AM item but DO NOT clutter the TOC (only Heading 1/2/3 styles feed the TOC field by default).
- **fast mode reorders content:** images in fast's JSON output come AFTER all the paragraphs on a page rather than interleaved at their true y-position. This means an image belonging to AM3394 ends up rendered below AM3030 in the body — a fundamental ordering bug we cannot fix in the converter because the source JSON is already wrong.
- **hybrid mode preserves reading order** (geometric layout is correct: image between AM3394 and AM3030 sits where it should), and **separates AM titles from body descriptions** correctly. But it has its own pathologies the converter has to filter:
  - **OCR-of-screenshot noise:** Docling runs OCR over every embedded image and emits the OCR'd UI labels as flat sibling paragraphs (login form fields, dialog buttons, table cell contents — 100+ noise paragraphs per release note). The converter drops any text element whose bbox center sits inside an image's bbox on the same page. See `collect_image_bboxes` + `is_inside_image`.
  - **Page chrome leak:** Docling does not classify page headers/footers as `header`/`footer` element types. The CAE corporate band ("Jetsched Communications Release Note", "AIR TRANSPORT INFORMATION SYSTEMS", "SAS CYBERJET …", "Page X sur N") and bare metadata fragments (version triple, MM/YYYY date) get emitted as body paragraphs. Filtered by `PAGE_CHROME_PHRASES` substring match + `PAGE_CHROME_RE` exact-match for version/date fragments.
  - **Cyberjet logo:** the small ~72×72pt logo in the top-left of every page is emitted as a body image. Filtered by `is_page_header_logo` (top-of-page position + small bounding box). Logo bboxes are EXCLUDED from the OCR-noise filter so we don't accidentally drop real text that sits just below the logo band.
- **Recurring extractor pathologies still in the output (V8.1.12.0 sample):** even after all filters, hybrid mode still wraps one continuation phrase ("Last valid EOBT", "Correctly displayed on the new column …") that visually belongs to a body paragraph but the extractor classifies as a separate fragment. These are minor and don't break the TOC, but they look ugly in the body. Worth a follow-up iteration.
- **Test data reality:** Only V8.1 PDFs available locally (`patches/ACARS_V8_1/{8.1.11.0,8.1.11.2,8.1.12.0,8.1.12.1,8.1.12.2}/release_notes/`). V7.3 and V8.0 family-difference checks deferred. The 5 V8.0 PDFs in `docs_example/pdf_examples/8.0/` already have pre-extracted fast-mode JSON in `extracted/fast/` which can be reused via the script's `--json` flag without re-running Java.
- **Output artifacts and review workflow:** the script writes both `<output>.docx` and `<output>.md` (the raw extractor markdown, copied from the cache for reference). Current outputs live in `docs_example/conversion_prototype/`:
  - `8.1.12.0.docx` + `.md` — fast mode result
  - `8.1.12.0_hybrid.docx` + `.md` — hybrid mode result
  - `.cache/{fast,hybrid}/<stem>.json` + `<stem>_images/` — extractor caches, reused on subsequent runs unless `--no-cache` is passed.
- **Verdict so far: NOT YET ACCEPTABLE.** Hybrid mode produces a clean enough hierarchy that the Word TOC auto-generates correctly (section → AM-item → bold sub-labels in body) and image ordering is right, but the body is still cluttered enough that the result is "below acceptable workflow quality" per Alex's review on 2026-04-11. Next iterations need to: collapse the orphaned continuation fragments into their parent paragraphs, run the same prototype against AM3030 and AM3388 patches to confirm the cleanup generalizes, and pull a V7.3 / V8.0 sample for family-difference review before declaring go/no-go.

---

### Unit 5 — Block B integrated ✅ DONE (2026-04-15)

**Effort:** Medium.
**Depends on:** units 3 + 4 (and 4 was a "go" on the Claude path — Unit 4.5).

**Scope as built.** Lift the Claude-mode parts of `scripts/test_docx_conversion.py` into `backend/app/pipelines/docs/converter.py` as **two public functions** (not one), wire them into the orchestrator as **two new sequential passes**, and clean up one pre-existing sub-step smell in the workflow status machine while we're at it.

**Why two stages, not one.** Extract (cache lookup + Claude API) and render (template + python-docx) have totally different failure-mode universes — extract is slow/networked/expensive, render is fast/local/free. Standard production-ETL pattern (Airflow tasks, Dagster ops, Prefect tasks, dbt nodes, Temporal activities) is discrete stages with their own state, their own retry semantics, and their own failure-mode counters. Splitting them gives clean per-stage logs and lets a render-only retry cost zero API dollars (cache hit on the extract pass).

**Workflow status changes.**
- **Added `extracted`** between `downloaded` and `converted`. Set by `extract_release_notes` on a successful cache hit or fresh API call.
- **Removed `discovered`** from `ReleaseNotesState`. It was a vestigial sub-step from Unit 3 that encoded "halfway through the fetch attempt" as a workflow value — failed the four-bullet test for "is this a real workflow stage". The fetcher now sets `source_url`, `source_pdf_path`, and `status = "downloaded"` together at the success path (single transition, `not_started → downloaded`). `discovered_at` was dropped from the model; Pydantic silently ignores it on load so existing state files are forward-compatible. **Binaries kept its `discovered` state** because there it's a real first-class state set by SFTP discovery before any download attempt.
- **Note:** `pdf_exported` (planned for Unit 10) currently fails the same four-bullet test. Don't add it when Unit 10 ships — fold it into the publish action and rely on `last_run.step` for triage.

**Side fields added.**
- `extracted_at`, `record_json_path`, `generated_docx_path` on `ReleaseNotesState` (workflow stage timestamps + artifact paths).
- `not_found_reason: Literal["no_match", "ambiguous_match"] | None` set by the fetcher on `ZendeskNotFound` / `ZendeskAmbiguous`. Side field, not a status split — Unit 8 reads it for differentiated UI copy without bloating the workflow `Literal`.

**Files (as built):**
- [backend/app/state/models.py](backend/app/state/models.py) — `Literal` updated, `discovered_at` dropped, four new fields added.
- [backend/app/pipelines/docs/fetcher.py](backend/app/pipelines/docs/fetcher.py) — collapsed `not_started → discovered → downloaded` into one transition; populates `not_found_reason`.
- [backend/app/pipelines/docs/converter.py](backend/app/pipelines/docs/converter.py) (new) — two public functions (`extract_release_notes`, `render_release_notes`) plus all the lifted template/render helpers and SHA256-keyed cache helpers (with `extractor_version` guard).
- [backend/app/services/orchestrator.py](backend/app/services/orchestrator.py) — added `_build_claude_client()`, Pass 4 (extract) and Pass 5 (render), five new summary counters per product.
- [backend/app/config.py](backend/app/config.py) — added `docs_template_path` and `docs_cache_dir` properties.
- [backend/app/services/patch_service.py](backend/app/services/patch_service.py) — `RELEASE_NOTES_TRANSITIONS` updated to the new state machine.
- **No changes to `lifecycle.py`** — the split design eliminates the need for mid-flight `step` updates that an earlier draft proposed.

**`claude.enabled` semantics.** Gates **API calls only**, not the convert pass. Pass 4 always runs. Cache hit → `extracted` for free. Cache miss + `enabled=true` → real API call. Cache miss + `enabled=false` → clean skip (workflow status untouched, `last_run.state=success`, `convert.extract.skipped reason=claude_disabled` log line). Dev mode gets the full pipeline including DOCX rendering on cached patches without paying anything.

**`extract_release_notes` returns a literal**: `"extracted"` on success, `"skipped_no_api"` on cache miss + disabled. The orchestrator captures it via a `result_holder = {"value": None}` closure through `run_cell` and uses it to count `notes_extract_skipped` separately from `notes_extracted`. `render_release_notes` returns `None` — every `extracted` patch is renderable.

**Tests (28 new/updated, 251 backend tests passing):**
- `backend/tests/test_docs_extract.py` (new, 4 tests) — cache hit, cache miss + no API → clean skip, extractor exception → fail via `run_cell`, stale cache version → re-extract.
- `backend/tests/test_docs_render.py` (new, 4 tests) — happy path against the real Flightscape template, missing template → fail with `step="render"`, missing record JSON → fail, idempotent re-render.
- `backend/tests/test_orchestrator_docs_pass.py` (extended) — added `TestBuildClaudeClient` (2 tests) and `TestExtractRenderPasses` (4 tests covering happy path, Pass 4 fail / Pass 5 skip, Pass 4 succeed / Pass 5 fail, and the `skipped_no_api` clean-skip path). Existing Pass 3 tests were patched to mock out the converter so they stay focused on Pass 3 behaviour.
- `backend/tests/test_docs_fetcher.py` (extended) — single-transition happy path, `not_found_reason: no_match`, `not_found_reason: ambiguous_match`. Existing tests that asserted the `discovered` intermediate state were updated to assert the final state directly.
- `backend/tests/conftest.py` — sample tracker JSON fixture updated to the new release_notes schema (drop `discovered_at`, add `extracted_at`).

**Smoke test verdict (2026-04-15):** ✅ PASS. Real end-to-end run against `8.0.18.1`: cache hit on extract ($0 cost), 13 items rendered into a 6.2 MB DOCX, status advanced `downloaded → extracted → converted`, all side fields populated. See HANDOFF.md → "Smoke test recipe" for the no-API setup.

---

### Unit 6 — Scan endpoint polish + refetch endpoints + scan history persistence ✅ DONE (2026-04-17)

**Effort:** Small–Medium.
**Depends on:** unit 5.

**Scope as built.** Retrofitted `POST /pipeline/scan` and `POST /pipeline/scan/{product_id}` with a 409 Conflict guard backed by a file-per-scan history store. Added two new endpoints for targeted and bulk release-notes refetch (the escape hatch for `not_found` patches that auto-scan deliberately skips — see §4.2) and one helper on the orchestrator that both endpoints share.

**Files (as built):**
- [backend/app/state/models.py](backend/app/state/models.py) — added `ScanRecord` (scan_id, trigger Literal, started_at, finished_at, products, counts, duration_ms).
- [backend/app/state/scan_history.py](backend/app/state/scan_history.py) (new) — `save_scan_record` / `finalize_scan_record` / `is_main_scan_running` / `list_recent_scans` / `load_scan_record` helpers. Atomic write mirrors `state/manager.py` (fcntl + `.tmp` + `os.replace`). Each helper accepts an optional `scans_dir=` arg for test isolation, same pattern as `load_tracker(state_dir=...)`.
- [backend/app/config.py](backend/app/config.py) — added `scans_dir` property (`PROJECT_ROOT / "state" / "scans"`).
- [backend/app/services/orchestrator.py](backend/app/services/orchestrator.py) — added `refetch_release_notes(product_id, patch_id)` helper that runs Pass 3 → Pass 4 → Pass 5 on a single cell with save-after-each-pass for partial-failure visibility. Returns an outcome dict (`{converted, downloaded, not_found, extract_skipped, not_eligible, already_running, failed}`).
- [backend/app/api/pipeline.py](backend/app/api/pipeline.py) — retrofitted scan endpoints with `_run_main_scan()` wrapper (409 guard + scan record + `_aggregate_counts()` summing the 11 existing orchestrator counters + `product_errors`). Added `POST /pipeline/scan/release-notes?version=<prefix>` bulk endpoint. **Note:** bulk endpoint must be declared before `/pipeline/scan/{product_id}` or FastAPI routes `"release-notes"` into the product-id path.
- [backend/app/api/patches.py](backend/app/api/patches.py) — added `POST /patches/{product_id}/{patch_id}/release-notes/refetch` (targeted). 404 for unknown patch, 409 for not-eligible workflow status, 200 with `outcome="already_running"` for per-cell lock collisions (not 409 — could be the legitimate main scan). Persists a `trigger="targeted"` scan record whose counts bucket records the final outcome.

**Locking asymmetry (§4.1 in practice).** `is_main_scan_running()` only inspects records whose trigger is in `{"cron", "manual"}`. Records with trigger `"targeted"` or `"bulk_docs"` never block a main scan because the per-cell lock (`last_run.state == "running"`) already guarantees no two triggers work on the same cell. Verified end-to-end by planting a fake `targeted` in-flight record and confirming `POST /pipeline/scan` did **not** return 409.

**Tests (25 new, 276 total passing):**
- `backend/tests/test_scan_history.py` (new, 13 tests) — save/load roundtrip, creates dir on first write, finalize sets fields, finalize-missing is a no-op, 6 cases for `is_main_scan_running` (empty dir / manual blocks / cron blocks / finalized-doesn't-block / targeted-doesn't-block / bulk-doesn't-block / missing dir), `list_recent_scans` sorts + limit + missing dir.
- `backend/tests/test_api_pipeline.py` — extended with 409-guard test, finalize-on-exception test, `TestBulkRefetch` class (version-prefix filter, outcome aggregation, not-blocked-by-main-scan).
- `backend/tests/test_api_patches.py` — added `TestRefetchReleaseNotes` class (success, 409 not-eligible, 200 already-running, 404 unknown patch, 200 not-found outcome).
- `backend/tests/conftest.py` — added `tmp_scans_dir` fixture.

**Smoke test verdict (2026-04-17):** ✅ PASS. Full end-to-end on the real FastAPI server with `docs.enabled=false`, no external calls. Verified: 4 endpoints in OpenAPI, scan record persists + finalizes even when SFTP raises, 409 guard fires on planted `manual` in-flight record, `targeted` in-flight does NOT block main scan (asymmetry), targeted refetch returns 404/409/200-already_running/200-failed(zendesk_unavailable) for each edge case, bulk refetch unfiltered = 34 candidates, `?version=8.1` narrows to 23 (ACARS_V8_1 only), all 7 scan records finalized.

---

### Unit 7 — File serving endpoints ✅ DONE (2026-04-17)

**Effort:** Small.
**Depends on:** unit 5.

**Scope as built.** Two `GET` endpoints on [backend/app/api/patches.py](backend/app/api/patches.py) that stream the release-notes artifacts for a given patch. Needed by unit 9's review view (source PDF on the left panel, DOCX-rendered-as-PDF on the right). No changes to state, services, or pipelines.

**Files (as built):**
- [backend/app/api/patches.py](backend/app/api/patches.py) — added `GET /patches/{product_id}/{patch_id}/release-notes/source.pdf` and `GET /patches/{product_id}/{patch_id}/release-notes/draft.docx`. Each handler resolves the patch via `find_patch()`, then applies three distinct 404 checks: (1) `PatchNotFoundError`, (2) the path field on `ReleaseNotesState` is `None` (pass 3 / pass 5 didn't run), (3) the file doesn't exist on disk (state references a cleaned-up path). Success returns `FileResponse(path, media_type=..., filename=f"{patch_id}-release-notes.{ext}")` with the right MIME type (`application/pdf` / `application/vnd.openxmlformats-officedocument.wordprocessingml.document`). First use of `FileResponse` in the codebase.
- Route shape follows the existing `{product_id}/{patch_id}` convention from every other patches route (the plan-doc shorthand `{id}` was expanded to match). URL paths end in `.pdf` / `.docx` as the plan specified.

**Tests (8 new, 284 total passing):**
- `backend/tests/test_api_patches.py` — added `TestGetSourcePdf` and `TestGetDraftDocx` classes, 4 cases each: success (mime + body bytes match), 404 when path is `None`, 404 when file missing on disk, 404 when `find_patch` raises `PatchNotFoundError`. Mirrors the `TestGetPatchDetail` style (mock `find_patch` + `tmp_path` for real files). Added a small `_tracker_with_release_notes()` helper alongside the existing `_make_tracker()`.

**Smoke test verdict (2026-04-17):** ✅ PASS. Real patch `ACARS_V8_0/8.0.18.1` (`converted` status from the Unit 5 smoke test). `curl` against `source.pdf` → 200, `application/pdf`, 5.8 MB, valid 35-page PDF. `curl` against `draft.docx` → 200, correct OOXML MIME, 6.2 MB, `content-disposition: attachment; filename="8.0.18.1-release-notes.docx"`. Negative cases: DOCX on a `downloaded`-only patch (`ACARS_V8_1/8.1.11.0`, no Pass 5 run) → 404 `{"detail":"Generated DOCX not available for this patch"}`; unknown patch id → 404 on both endpoints. Note: `curl -I` (HEAD) returns 404 because FastAPI doesn't auto-register HEAD for `@router.get` — not required for Unit 9 consumers (browsers issue GET).

**Done criteria:** met. `curl -O` downloads usable files in dev against a real converted patch; full suite (276 → 284) stays green.

---

### Unit 8 — UI: additive changes (badge, run indicator, refetch action, detail modal) ✅ DONE (2026-04-19, smoke test pending)

**Effort:** Medium.
**Depends on:** unit 6.

**Scope as built.** All the additive changes to the existing [Pipeline.tsx](frontend/src/views/Pipeline.tsx) and [PatchDetailModal.tsx](frontend/src/components/patches/PatchDetailModal.tsx) **except** the side-by-side review view (that's unit 9). Workflow status badges stay where they are. No layout changes. One small backend prerequisite surfaced during implementation (see first file below).

**Files (as built):**
- [backend/app/api/patches.py](backend/app/api/patches.py) — `_patch_summary()` now projects `last_run` on both tracks (was previously dropped). Without this the Pipeline list view couldn't render running/failed indicators — only the detail endpoint serialized `last_run`. Uses `model_dump(mode="json")` to match the datetime serialization the detail endpoint already does.
- [backend/tests/test_api_patches.py](backend/tests/test_api_patches.py) — extended `TestListAllPatches::test_splits_actionable_history` with assertions that both `binaries.last_run.state` and `release_notes.last_run.state` come back as `"idle"` (the model default).
- [frontend/src/lib/types.ts](frontend/src/lib/types.ts) — added `LastRunState`, `LastRun`, `RefetchOutcome`, `RefetchReleaseNotesResponse`, `BulkRefetchResponse`, `BulkRefetchResult`. Extended `PatchStatus` with `"not_found"` and `"extracted"` (the latter was already valid on the backend and missing in the frontend union). Added `last_run: LastRun` to `BinariesState` and `ReleaseNotesState`, and threaded it through the `PatchSummary` `Pick`s for both tracks.
- [frontend/src/lib/constants.ts](frontend/src/lib/constants.ts) — `not_found` entry added to `STATUS_CONFIG` with a muted red palette (`#ef4444` dot, `#fca5a5` text, `rgba(239,68,68,0.12)` bg) — distinct from a crash, reads as "we looked, Zendesk had nothing".
- [frontend/src/lib/api.ts](frontend/src/lib/api.ts) — `refetchReleaseNotes(productId, patchId)` (targeted, `POST /patches/.../release-notes/refetch`) and `refetchReleaseNotesBulk(version?)` (bulk, `POST /pipeline/scan/release-notes?version=...`). Bulk is wired but no UI entry point in this unit (plan didn't specify one; deferred until needed).
- [frontend/src/components/shared/StatusBadge.tsx](frontend/src/components/shared/StatusBadge.tsx) — accepts optional `lastRun?: LastRun` and `onRetry?: () => void`. Renders a blue `Loader2` spinner when `lastRun.state === "running"`. Renders a small red-dot button when `lastRun.state === "failed"` — hover shows a native `title` tooltip with `step`, `error`, `finished_at` + "Click to retry" hint; click invokes `onRetry` (with `stopPropagation` so it doesn't also open the detail modal). Used native `title` instead of introducing a tooltip component — zero deps, matches the project's simplicity preference.
- [frontend/src/views/Pipeline.tsx](frontend/src/views/Pipeline.tsx) — both `StatusBadge` instances now receive `lastRun`; the release-notes badge additionally passes `onRetry={() => handleRefetchReleaseNotes(p)}`. New `handleRefetchReleaseNotes` callback lives alongside `handleApproveSuccess`: calls the targeted refetch API, maps each `outcome` value to an appropriate `toast.success/error/info` message, then invalidates the `patches` and `dashboard-summary` queries so the UI refreshes. In the Actions column, the "Approve Docs" button is replaced by a "Refetch Docs" button (with `RefreshCw` icon) when `release_notes.status ∈ {"not_started", "not_found"}`. Button is disabled while `last_run.state === "running"` — the backend already guards with `already_running`, but the UI disable gives immediate feedback.
- [frontend/src/components/patches/PatchDetailModal.tsx](frontend/src/components/patches/PatchDetailModal.tsx) — new `LastRunSection` subcomponent rendered below the timeline in both the binaries and release-notes columns, just above the approve button. Shows `state` with a state-specific color (idle=muted, running=blue, success=green, failed=red), a spinner when running, and `step` / `started_at` / `finished_at` / `error` when populated. When idle with no timestamps, renders `"No run yet"`. Error text is shown in a mono block clamped to 3 lines via `-webkit-line-clamp`; full text in the `title` attribute.

**Tests (1 new assertion, 284 total passing):**
- Backend: added the `last_run` presence check to the existing list-endpoint test. Full suite (`pytest tests/ -k "not integration"`) green: 284 passed.
- Frontend: `npx tsc -b` — all Unit 8 files compile clean. See "Known issue" below for a pre-existing blocker.

**Smoke test:** PENDING. Deferred until Alex can exercise the UI end-to-end in dev mode against a real patch (targeted refetch against Zendesk, forced failure for the red-dot retry, and detail-modal `LastRunSection` rendering). The code paths are all wired but no browser verification has been done yet.

**Known issue surfaced during verification (NOT introduced by Unit 8):**
- `cd frontend && npm run build` is broken on `main` before this unit's changes. Three `TS6133` unused-declaration errors in [frontend/src/components/patches/JiraApprovalModal.tsx](frontend/src/components/patches/JiraApprovalModal.tsx):
  - Line 151 — `onSuccess` prop declared but never read.
  - Line 180 — `setSubmitting` from `useState` declared but never read.
  - Line 182 — `setSubmitError` from `useState` declared but never read.
  Verified by stashing Unit 8 changes and re-running the build — the errors predate this unit (last touched in commit `2401beb F4 polish: modal layout fixes…`). `tsc` on the files touched by Unit 8 passes cleanly; the build blocker lives entirely in `JiraApprovalModal.tsx`. **Flagged as the first item to handle at the start of the next unit** — likely a trivial mechanical cleanup (either wire the unused state through or drop it). Tracked in HANDOFF.md → "Next unit to check".

**Done criteria:** code-complete. Full end-to-end smoke test against a real `not_found` / `failed` patch in dev is the remaining gate before declaring the unit fully shipped.

---

### Unit 9 — UI: side-by-side review view ✅ DONE (2026-04-20)

**Effort:** Medium.
**Depends on:** units 7 + 8.

**Scope.** Review view with two panels — source PDF on the left, rendered DOCX on the right — plus an "Open in Word" button that opens the local DOCX file on the user's machine. **No in-browser record editor** (decided 2026-04-15): if content looks wrong Alex opens Word, tweaks manually, and the tweak lives in the downstream DOCX. If the bug is systematic, it goes into the template or `render_record()` code once — not per-release UI edits.

The view is a **gate in front of** the existing `JiraApprovalModal`, not a replacement for it.

**Why DOCX is rendered as PDF for display.** Browsers can't natively render DOCX. The backend converts `generated_docx_path` → PDF on-the-fly via `libreoffice --headless` for the right panel's display. This is **display-only** — the canonical artifact stays the DOCX on disk; the PDF is a cached preview.

Flow:
1. Click "Approve Docs" on a `converted` release-notes cell → `DocsReviewView` opens.
2. Source PDF on the left (via Unit 7's `GET /patches/{p}/{v}/release-notes/source.pdf`, rendered with pdf.js or `<embed>`).
3. Converted DOCX on the right, shown as PDF (new endpoint converts DOCX → PDF via `libreoffice --headless`, cached by file mtime).
4. "Open in Word" button — opens the local `generated_docx_path` on Alex's machine so he can tweak manually if needed. No back-trip to the browser; any manual edits stay in that local DOCX file.
5. "Looks good, continue" button → closes the review view and opens the existing `JiraApprovalModal`, pre-filled for the docs ticket. No new Jira UI — reuse what binaries already uses.
6. Jira modal approve → existing `POST /patches/{p}/{v}/docs/approve` endpoint → Unit 10's publish flow kicks in on the backend.

The review view itself does **not** advance workflow status — `converted → approved` still happens through the Jira modal + approve endpoint, same pattern as binaries.

**Files:**
- `frontend/src/components/patches/DocsReviewView.tsx` (new) — two-panel viewer (PDF left, DOCX-rendered-as-PDF right), "Open in Word" button, "Looks good, continue" button. Emits a `continue` callback; the parent (Pipeline.tsx) opens `JiraApprovalModal` on it.
- [frontend/src/views/Pipeline.tsx](frontend/src/views/Pipeline.tsx) — chain the existing "Approve Docs" path: open `DocsReviewView` first, then on continue open the existing `JiraApprovalModal`. Binaries "Approve" path is untouched.
- `backend/app/api/patches.py` — add `GET /patches/{p}/{v}/release-notes/preview.pdf` that returns the DOCX converted to PDF. Runs `libreoffice --headless --convert-to pdf <generated_docx_path> --outdir <cache>`, caches the result by DOCX mtime, returns the PDF. Regenerates if the DOCX was re-rendered.
- **Optional** (macOS dev convenience, if `file://` links misbehave in the browser): `POST /patches/{p}/{v}/release-notes/reveal` that runs `subprocess.run(["open", path])` to open the DOCX locally in Word.

**What's explicitly NOT in Unit 9 anymore** (dropped 2026-04-15):
- Record editor UI (edit items/blocks/images in the browser).
- `POST /patches/{p}/{v}/release-notes/render` endpoint for re-rendering from an edited record. The `render_release_notes()` function stays available for programmatic use, but no endpoint exposes it.
- Any "save and re-render" loop. DOCX is final once Pass 5 wrote it; the only edits happen in Word on Alex's local machine and are part of the final approved artifact.

**LibreOffice dependency.** Unit 9 introduces `libreoffice --headless` as a runtime dependency on the dev machine. Documented in setup instructions. Fine for dev; a future prod deployment would need the same binary available. It's also used by Unit 10 for the final DOCX → PDF export, so the dependency isn't unique to Unit 9.

**Tests.** `npm run build` clean. Manual smoke test: open the review view on a real `converted` patch, see the source PDF on the left and the rendered DOCX-as-PDF on the right, click "Open in Word" and confirm the local DOCX opens in Word on your machine, click continue, see the Jira modal appear pre-filled, approve, confirm state advances `pending_approval → approved → published` (Unit 10 handles the final transition).

**Done criteria:** end-to-end docs review workflow works against real Zendesk-fetched release notes.

**As built (2026-04-20):**
- New [backend/app/pipelines/docs/exporter.py](backend/app/pipelines/docs/exporter.py) — `export_docx_to_pdf(docx_path, out_dir=None) -> Path`, shells out to `soffice --headless --convert-to pdf`, caches by mtime, idempotent. `_resolve_soffice()` checks `LIBREOFFICE_BIN` env → `shutil.which("soffice")` → `/Applications/LibreOffice.app/Contents/MacOS/soffice`. Will be reused by Unit 10.
- New endpoint in [backend/app/api/patches.py](backend/app/api/patches.py): `GET /patches/{p}/{v}/release-notes/preview.pdf` — converts via `export_docx_to_pdf`, cache at `state/cache/pdf/{product_id}/{version}.pdf`. 503 if `soffice` missing; 500 on conversion failure; 404 if DOCX missing.
- New endpoint: `POST /patches/{p}/{v}/release-notes/open-in-word` — runs `subprocess.run(["open", path])` so macOS launches the canonical DOCX in Word. Chose `open-in-word` over `reveal` because macOS "reveal" means show-in-Finder (wrong action). `file://` links rejected (browsers block them); `ms-word:ofe|u|` rejected (opens a temp copy, edits don't persist).
- [backend/app/config.py](backend/app/config.py) — added `LIBREOFFICE_BIN` env field and `docs_preview_cache_dir` property. Dev-machine setup: `brew install --cask libreoffice` (done).
- New [frontend/src/components/patches/DocsReviewView.tsx](frontend/src/components/patches/DocsReviewView.tsx) — full-bleed modal (not a route), two `<iframe>` panels, header has "Open in Word" button left of close-X, footer has Cancel + Continue. Per-mount cache-bust via `?v=${Date.now()}` on iframe srcs so Chrome doesn't reuse a cached `Content-Disposition: attachment` decision.
- Modified [frontend/src/views/Pipeline.tsx](frontend/src/views/Pipeline.tsx) — `openApproval` routes docs through a new `reviewView` state; continue callback closes review and opens `JiraApprovalModal` with `pipelineType: "docs"`. Binaries path untouched. Button-enablement loosened from `pending_approval` to `converted | pending_approval` so Unit 9's review gate is actually reachable (otherwise nothing could open it — `converted` is the natural state where the DOCX exists). Same loosening applied to [frontend/src/components/patches/PatchDetailModal.tsx](frontend/src/components/patches/PatchDetailModal.tsx); detail-modal button relabeled to "Review & Approve Release Notes".
- [frontend/src/lib/api.ts](frontend/src/lib/api.ts) — added `openDocxInWord(productId, patchId)` helper. Preview PDFs are consumed as raw URLs by the iframe — no typed fetch helper needed.
- Both `source.pdf` and `preview.pdf` responses set `content_disposition_type="inline"` so they render in the iframe instead of triggering a download.

**Tests:** 22 new backend tests (`TestGetPreviewPdf` × 6, `TestOpenDocxInWord` × 4, `test_docs_exporter.py` × 12). Full suite: 306 passed, 6 skipped, 11 deselected. Frontend `tsc -b && vite build` clean.

**Known issue discovered during smoke: stale TOC cache in DOCX → LibreOffice preview shows template boilerplate.** The DOCX that Unit 5 writes contains a `TOC` field with `dirty="1"` set (telling viewers to regenerate on open). Word honors `dirty` and regenerates the TOC from current body headings — shows real release-notes headings correctly. LibreOffice ignores `dirty` and renders the field's cached text, which still contains template placeholder entries ("Introduction", "Insert your Heading", "Delete This Chapter…") from the source template. Verified by: (a) grepping `w:dirty="1"` in the DOCX's `document.xml`, (b) comparing body `<w:pStyle w:val="Heading1|2">` paragraph text (all real release-notes content) against the cached TOC text runs (all template). Unit 9's preview is faithfully rendering what LibreOffice produces; the stale cache itself is the defect. Preview still shows the rest of the DOCX (body sections, formatting, images) accurately — only fields like TOC are stale. **Fix is Unit 11.**

---

### Unit 10 — DOCX → PDF on approval, attached to Jira docs ticket

**Effort:** Small–Medium.
**Depends on:** unit 9.

**Scope.** Final transition. After a docs cell is approved, convert the approved DOCX to PDF and attach the PDF (not the DOCX) to the docs Jira ticket, then advance to `published`. Single transition `approved → published` — **no intermediate `pdf_exported` workflow status**.

**Why no `pdf_exported` state** (decided during Unit 5, applying the four-bullet rule to the whole state machine): PDF export and Jira attachment both happen inside the same publish action with the same failure-mode universe. A `pdf_exported` intermediate would be a sub-step of "publish" dressed up as a workflow state — the same smell Unit 5 fixed by collapsing `discovered` on release notes. Instead, triage info lives on `last_run.step` (e.g. `step="pdf_export"` if LibreOffice fails, `step="jira_attach"` if the Jira call fails). The workflow status field stays focused on business stages only.

**Files:**
- `backend/app/pipelines/docs/exporter.py` (new) — `export_docx_to_pdf(docx_path) → pdf_path`. Thin wrapper around `libreoffice --headless --convert-to pdf` (already a dev-machine dependency for Unit 9's preview endpoint, so no new infra). Output path: next to the DOCX as `<version>.pdf`. Idempotent: if the output PDF is newer than the DOCX, skip the conversion.
- [backend/app/services/patch_service.py](backend/app/services/patch_service.py) — extend the docs approve flow as a single `run_cell(step_name="publish")`: (1) export DOCX → PDF, (2) create Jira ticket, (3) attach the PDF, (4) set `cell.status = "published"`. All three sub-steps live inside one work function.
- `backend/app/state/models.py` — **drop `pdf_exported`** from `ReleaseNotesState.status` Literal. Also drop `pdf_exported_at`. Pydantic silently ignores them on load from any existing state files (same forward-compat pattern as Unit 5's `discovered` removal).

**Triage on failure.** With `step_name="publish"` shared across all three sub-steps, `last_run.step` alone doesn't tell you which sub-step crashed. That's OK because each sub-step raises a distinctive exception type (python-docx/LibreOffice errors from export, `JiraAPIError` with an HTTP status code from create/attach) — the exception class name and message already pin down the phase. The traceback in the rotating log file closes any remaining ambiguity. If we ever need sharper triage (e.g. Grafana alerts differentiating "export broken" from "Jira broken"), the cheapest fix is to make `lifecycle.py` prepend `type(exc).__name__` to the stored error field (~2 lines). Don't design for that until it's needed.

**Idempotency on retry.**
- PDF export: re-running is cheap (local LibreOffice); the output path is the same regardless.
- Jira create: `patch_service` already has a "two-step save" pattern from the binaries flow — if a ticket was created in a previous attempt, its key is persisted on the cell, and retries reuse it.
- Jira attach: idempotent per the existing Jira client behavior.

So a failed publish attempt leaves the cell at `approved` (workflow status untouched) and the next manual retry works cleanly, regardless of which sub-step failed last time.

**Tests.**
- Unit: exporter produces a valid PDF from a fixture DOCX; running twice with no DOCX change is a no-op.
- Integration: full docs approve flow takes a `pending_approval` cell (set either by Unit 9's review-view "continue" button or by a direct API call on a `converted` cell) all the way to `published` with a real Jira ticket key and PDF attachment (against a Jira fixture / mock).
- Partial-failure retry: Jira attach fails on first attempt → cell stays at `approved` (workflow status untouched by the publish work function), `last_run.state=failed`. Second attempt reuses the already-exported PDF (local file exists) and the already-created Jira ticket key (persisted on the cell) and re-tries just the attach.

**Done criteria:** at least one real docs ticket created in dev with a converted PDF attachment, and the cell's final state is `published`.

---

### Unit 11 — Fix stale TOC cache in rendered DOCX

**Effort:** Small–Medium.
**Depends on:** unit 5 (render_release_notes). Should land **before** unit 10 so the final approved PDF attached to Jira has a correct TOC, not a stale one.

**Scope.** The DOCX that [render_release_notes()](backend/app/pipelines/docs/converter.py) writes contains a `TOC` field copied from the Flightscape template. The body is correctly populated with H1/H2 headings for the new release content ("New Features", "Defect fixes", "Not tested", AM#### items). But the field's cached inline content — the runs between `<w:fldChar w:fldCharType="separate"/>` and `<w:fldChar w:fldCharType="end"/>` — still holds the template's placeholder entries ("Introduction", "Insert your Heading", "Delete This Chapter…"). The field is marked `w:dirty="1"` so Word regenerates on open (visible to reviewers), but LibreOffice ignores `dirty` and renders the stale cache. Result: Unit 9's preview panel shows template boilerplate; Unit 10's to-be-attached PDF would do the same unless fixed. Discovered while smoke-testing Unit 9 against patch 8.0.18.1 on 2026-04-20.

This is a Unit 5 defect — the DOCX on disk is wrong. Fixing in Unit 5 means Unit 9 preview and Unit 10 publish PDF both get correct output automatically.

**Two candidate approaches.** Pick one after a short spike:

1. **XML surgery in [render_release_notes()](backend/app/pipelines/docs/converter.py).** After the body is populated, walk the document and for each TOC field:
   - Collect the current H1-H5 paragraph texts + their assigned page numbers.
   - Replace the runs between `separate` and `end` `fldChar` elements with freshly-generated hyperlinked entries.
   - Keep `w:dirty="1"` so Word still regenerates (defensive).

   Pros: no new runtime dependencies; DOCX on disk is self-contained and correct for any viewer. Cons: page numbers are tricky — we don't know real page breaks until a renderer lays the doc out. One workable shortcut: leave the page numbers blank or `…` in the cache; since Word regenerates on open and LibreOffice renders the cache, a blank-page-number cache is acceptable for LibreOffice preview (shows the right headings, just no page refs). Humans reading the preview care about heading structure, not page numbers.

2. **Pre-convert update via python-uno.** In [export_docx_to_pdf()](backend/app/pipelines/docs/exporter.py), instead of `soffice --convert-to pdf`, run a small python-uno helper (under LibreOffice's bundled Python at `/Applications/LibreOffice.app/Contents/Resources/python`) that connects to a headless soffice listener, loads the DOCX, calls `doc.DocumentIndexes.getByIndex(i).update()` for each index, then exports to PDF.

   Pros: works on any DOCX with stale fields, not just TOCs we emit. Cons: adds soffice listener startup (~1s per first call), more moving parts, and the DOCX on disk stays stale — so `draft.docx` download and Word open still get the stale cache until Word does its on-open regen.

**Recommendation: option 1 (fix at render time).** Keeps the on-disk DOCX correct and doesn't add a conversion-time dependency beyond what we already shipped in Unit 9. If page numbers turn out to be impossible without a layout pass, fall back to blank page numbers in the cache — still displays correct heading structure in LibreOffice preview, and Word users get real page numbers via the on-open regeneration. Unit 10's approved PDF is generated by LibreOffice too (same stale-cache problem), so we'd also add a `dirty="1"` check or just trust that option 1 produced a correct cache.

**Files:**
- [backend/app/pipelines/docs/converter.py](backend/app/pipelines/docs/converter.py) — add a `_regenerate_toc_cache(doc)` helper called after body population; rewrite runs between `separate` and `end` `fldChar` for each TOC field.
- `backend/tests/test_docs_converter.py` (extend) — fixture DOCX with a stale TOC cache + real body headings; assert the post-render DOCX's cached TOC entries match the body headings.
- `backend/tests/fixtures/docx/…` — minimal template DOCX with a TOC field for testing.

**Tests.**
- Unit: given a DOCX with stale TOC cache and body headings `["New Features", "Defect fixes"]`, after `render_release_notes()` the cached TOC text runs contain exactly those heading labels (and not the template placeholders).
- Integration: regenerate `8.0.18.1.docx` end-to-end, open Unit 9's preview, confirm the TOC panel shows "New Features / Defect fixes / Not tested" instead of "Introduction / Insert your Heading / …".

**Done criteria:** Unit 9 preview of any newly-rendered DOCX shows a TOC matching Word's rendering. No regression in Word's own display (Word still regenerates fields on open).

---

### Future ideas — extraction quality gates

Three ideas borrowed from a colleague's agentic PDF parsing pipeline (RAG-focused), worth stealing for our review workflow:

1. **Untagged-content bucket.** Add `untagged_content: list[str]` to `ReleaseNoteRecord`. After extraction, run Tesseract (or pdfplumber's text layer) over the PDF, diff OCR tokens against everything Claude placed in section/heading/paragraph/list/table/code blocks, and drop the leftover runs into the bucket — grouped by page. Nothing is ever silently dropped: the Unit 9 review view surfaces exactly what Claude skipped so a reviewer can place it or confirm it's chrome. Watch out for false positives from text inside screenshots (system prompt says don't transcribe them) — subtract image-bbox tokens from the OCR ground truth first using the existing `collect_image_bboxes` logic.

2. **Coverage-ratio gate.** Compute `|claude_tokens ∩ ocr_tokens| / |ocr_tokens|` (after image-bbox subtraction) and fail the extract pass if below a threshold (his article uses 0.95). Gives us a regression signal when a new release-notes layout lands and Claude starts leaking chrome into body text — today we'd only notice by eye.

3. **Retry loop with feedback.** If the coverage gate fails, re-run the extraction with the untagged fragments injected as a hint in the system message ("previous run missed these fragments, place them"). Cap at 3 attempts via a config key. With prompt caching on the PDF + schema + system prompt, each retry costs ~$0.22, so the safety net is near-free.

Implementation order: (1) first — high value, cheap, no retry plumbing. (2) second — needs (1). (3) last — only if production shows failures that retries actually fix.

---

### Block-to-unit mapping (for cross-reference)

| Block in §2 | Units in §7 |
|---|---|
| Block A — Zendesk fetcher | Unit 3 |
| Block B — DOCX template injection | Units 4 (prototype) + 5 (integrated) |
| Block C — Merge into approval flow | Units 6 (API) + 7 (file serving) + 8 (UI additive) + 9 (review view) + 10 (DOCX→PDF) |
| Foundational (not in §2) | Units 0 (logging) + 1 (state model) + 2 (lifecycle helper) |