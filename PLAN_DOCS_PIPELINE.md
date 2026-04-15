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
- State transition on `release_notes`: `not_started → discovered → downloaded`.
- New fields on `ReleaseNotesState`: `source_pdf_path`, `source_url`, `source_published_at`.

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
- A main scan is the three-pass flow from §4.0. The docs pass auto-acts on `not_started` only — never `not_found` (see §4.2 for the asymmetry).
- The existing [Pipeline.tsx](frontend/src/views/Pipeline.tsx) table is already structured right: one row per patch, two status-badge columns, two approval buttons. **All UI changes are additive** — workflow status badges stay exactly as they are. Filter bar, history table, approval modal, overall layout: unchanged.
- Approving binaries and approving docs are still independent buttons / endpoints / Jira tickets. The docs side has one extra final step: after approval, convert the approved DOCX to PDF and attach *that* to the docs Jira ticket. State: `approved → pdf_exported → published`.

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

**`ReleaseNotesState.status`** (one new value: `not_found`):
```
not_started ─┬─ discovered → downloaded → converted → pending_approval → approved → pdf_exported → published
             │
             └─ not_found  ◀── Zendesk lookup ran cleanly, no matching article yet
```

`not_found` is the only addition. It means "we looked, Zendesk doesn't have it yet" — a soft, expected outcome since notes are often published after the binaries land on SFTP. Re-entered from `not_started` and exited back to `discovered` on a future successful scan.

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
    status: Literal["not_started", "discovered", "downloaded", "converted",
                    "pending_approval", "approved", "pdf_exported", "published",
                    "not_found"] = "not_started"
    last_run: LastRun = LastRun()
    # + existing timestamps, jira fields
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
   - Advance `status` (workflow) if appropriate — e.g. docs fetch `not_started → discovered`, or `not_started → not_found` on clean negative.
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

A main scan is **three sequential passes over the same state**, each independent. SFTP discovery writes new patches to state *before* any download happens — the moment a patch is discovered, it exists in the system as a tracked entity, with `binaries.status = discovered` and `release_notes.status = not_started`. From that moment on, the two tracks progress independently.

```
POST /scan (main scan):

  1. SFTP DISCOVERY
     ─ list SFTP, find new patches
     ─ write to state immediately:
         binaries.status      = discovered
         release_notes.status = not_started
     ─ the patch is now tracked, even though nothing is downloaded yet

  2. BINARIES PASS — for each cell where binaries.status == discovered
                     AND last_run.state != "running":
     ─ run the per-cell lifecycle (section 3.4)
     ─ on success: binaries.status moves discovered → downloaded → pending_approval
     ─ on failure: binaries.last_run.state = failed, workflow status untouched

  3. DOCS PASS — for each cell where release_notes.status == not_started
                 AND last_run.state != "running":
     ─ run the per-cell lifecycle — fetch from Zendesk
     ─ if found:        status moves not_started → discovered → downloaded → ...
     ─ if cleanly not:  status = not_found, run state = success
     ─ if exception:    run state = failed, workflow status untouched

  4. Persist scan record to state/scans.json with counts for each pass.
```

**Critical: the docs pass auto-acts on `not_started` only, NEVER on `not_found`.**

This is the most important rule in the docs pipeline and it's worth being loud about.

The naive approach would be to also auto-retry `not_found` patches on every scan ("maybe the notes are published now"). That's the **trap**: every cron tick would re-hit Zendesk for every patch still missing notes, and the eligibility set grows monotonically as the backlog accumulates. One misconfigured backoff away from getting the scraper IP blocked. Linear-in-backlog load on a third-party Cloudflare-protected site is exactly what you don't want.

Instead: **publishing release notes is the developer's job, not the cron's job to keep guessing.** When notes are published, the recovery mechanism is explicit human (or future automated) action, not blind polling:

- **Today:** Alex sees `not_found` in the UI and clicks the "Refetch Release Notes" action button on that row.
- **Future:** an email webhook (or any other "notes are now available" signal) hits the targeted refetch endpoint. Same code path, no design change.

Auto-fetch acts on patches that have **never been tried** (`not_started`); manual / future-webhook acts on patches that have been tried and came up empty (`not_found`). Two different intent levels, two different trigger mechanisms, one shared per-cell lifecycle.

**Why three sequential passes and not interleaved:**
- A binaries failure in pass 2 does not block the docs pass for the same patch — the two tracks are independent at the cell level.
- Sequential passes keep logs readable and isolate external-system blast radius (SFTP issues vs Zendesk issues). Parallelizing later is a small change if scan volume ever demands it.

### 4.1 Two kinds of scan

These are different enough that they get different endpoints, different log namespaces, and different locking rules:

| | **Main scan** | **Targeted docs fetch** |
|---|---|---|
| **Scope** | Walks SFTP, discovers new patches, fans out to binaries download + docs fetch for everything new or retry-eligible | One (or N) specific known patch(es). Does not touch SFTP. |
| **Trigger** | Cron or "Start scan" button | UI row action or bulk version-header button |
| **Endpoint** | `POST /scan` | `POST /patches/{id}/release-notes/refetch` (single), `POST /scan/release-notes?version=...` (bulk) |
| **Log namespace** | `scan.main.*` | `zendesk.fetch.*` (direct, no `scan.*` wrapping) |
| **Locking** | Rejects if another main scan is running (409 Conflict) | Allowed during a main scan, because the per-cell lock (`last_run.state == running`) prevents double-work on the same cell |
| **Purpose** | Discover + progress everything in one sweep | "I know this specific patch needs its notes — don't make me wait for the next cron tick" |

The targeted fetch reuses the same Zendesk code internally, but it's a different workflow: the main scan discovers new work, the targeted fetch acts on a specific known cell. Don't conflate them.

### 4.2 Retrigger — three layers, one code path

All three layers call the same per-cell attempt function. The state is the queue — there is no separate retry table. The key asymmetry is **what counts as eligible** depending on who's triggering.

| Layer | Trigger | Eligible cells | Purpose |
|-------|---------|----------------|---------|
| **Auto on main scan** | Every `POST /scan` (cron or manual) | `release_notes.status == not_started` AND `last_run.state != running` | First-look only. Acts on patches that have never been tried. Bounded by definition — `not_found` is excluded so the eligibility set doesn't grow with the backlog. |
| **Per-row manual** | UI "Refetch Release Notes" action button on a single patch | `release_notes.status ∈ {not_started, not_found}` AND `last_run.state != running` | Alex (or a future webhook) saying "look again now, the developer just published". Explicit human intent — `not_found` is fair game here. |
| **Bulk** | Version-header button or filtered API call (`POST /scan/release-notes?version=...`) | same as per-row manual | Same explicit-intent semantics, but for a batch — e.g. "Refetch all missing notes in V8.1" after the developer announced a doc drop. |

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

## 5. Open questions to decide before building

These are decisions, not unknowns. Each one needs a yes/no before the relevant block starts.

1. **Block A:** Are Zendesk article titles 100% standardized to `<version> - Release Notes.pdf`, or do we need fuzzy matching? → check 5–10 real articles across V7.3, V8.0, V8.1.
2. **Block A:** What's the auth model — service account credentials in `.env`, same as Jira? → confirm Alex pastes credentials himself per the standing rule.
3. **Block B:** Run a standalone PDF→DOCX prototype against 3 representative real PDFs *before* wiring into the pipeline. If fidelity is bad, the whole plan changes (e.g. we may end up with a "human edits the DOCX" loop instead of full auto).
4. **Block C:** DOCX preview in browser — v1 is "download to review" or do we invest in HTML rendering up front?
5. **State:** Do we retrofit `last_run` onto existing state JSON files in one migration step, or lazily default to `idle` on load? Lazy is simpler but means no historical run data until the first attempt.
6. **State:** Scan history storage — single `state/scans.json` file (simple, gets large) or `state/scans/<scan_id>.json` (many small files, rotation-friendly)?

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
- `backend/app/pipelines/docs/fetcher.py` (new) — `fetch_release_notes(patch)`: calls the client, on success downloads PDF + transitions workflow status `not_started → discovered → downloaded`, on clean-negative transitions to `not_found`, on exception lets the lifecycle helper record the failure.
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

### Unit 6 — Scan endpoints + scan history persistence

**Effort:** Medium.
**Depends on:** unit 5.

**Scope.** Three new API endpoints + scan history storage. **No UI yet** — endpoints are usable from curl / OpenAPI docs.

**Files:**
- `backend/app/api/pipeline.py` (existing or new) — `POST /scan` (main scan, returns 409 if another main scan is running per the `finished_at IS NULL` check from §4.3), `POST /patches/{id}/release-notes/refetch` (targeted, allowed during a main scan because per-cell lock handles it), `POST /scan/release-notes?version=...` (bulk, calls targeted in a loop).
- `backend/app/state/scan_history.py` (new) — `ScanRecord` Pydantic model + `save_scan_record()` / `is_main_scan_running()` / `list_recent_scans()` helpers. Storage: **`state/scans/<scan_id>.json`** (decided in §5 question 6 — many small files, rotation-friendly, no need to load history into memory for the running-check).
- `backend/app/state/models.py` — add `ScanRecord` model.

**Tests.**
- POST /scan starts a main scan, writes a ScanRecord with `finished_at: null`, second POST /scan immediately returns 409.
- POST /patches/{id}/release-notes/refetch is allowed during a main scan; if the cell is already `running`, returns a clear "already in progress" response.
- Bulk endpoint loops correctly and reports per-cell outcomes.
- `is_main_scan_running()` returns `True` while a scan record has no `finished_at` and `False` after.

**Done criteria:** all three endpoints visible in `/docs` Swagger, exercised with curl in dev, scan records appear in `state/scans/`.

---

### Unit 7 — File serving endpoints

**Effort:** Small.
**Depends on:** unit 5.

**Scope.** Serve the source PDF and generated DOCX for a given patch's release notes. Needed by unit 9's review view. Tiny but isolated so it can ship independently.

**Files:**
- `backend/app/api/patches.py` (existing) — `GET /patches/{id}/release-notes/source.pdf` and `GET /patches/{id}/release-notes/draft.docx`. Both return the file with correct `Content-Type`. 404 if the file doesn't exist on disk.

**Tests.**
- Both endpoints return file content for a fixture patch with both files.
- 404 when files are missing.
- Correct Content-Type headers.

**Done criteria:** `curl -O` against both endpoints downloads usable files in dev.

---

### Unit 8 — UI: additive changes (badge, run indicator, refetch action, detail modal)

**Effort:** Medium.
**Depends on:** unit 6.

**Scope.** All the additive changes to the existing [Pipeline.tsx](frontend/src/views/Pipeline.tsx) and [PatchDetailModal.tsx](frontend/src/components/patches/PatchDetailModal.tsx) **except** the side-by-side review view (that's unit 9). Workflow status badges stay where they are. No layout changes.

**Files:**
- [frontend/src/lib/constants.ts](frontend/src/lib/constants.ts) — add `not_found` entry to `STATUS_CONFIG` with appropriate badge style.
- [frontend/src/lib/types.ts](frontend/src/lib/types.ts) — add `LastRun` type and extend `BinariesState` / `ReleaseNotesState` types to include `last_run`.
- [frontend/src/components/shared/StatusBadge.tsx](frontend/src/components/shared/StatusBadge.tsx) — accept an optional `lastRun` prop, render a small spinner icon when `last_run.state == "running"`, render a small red dot when `last_run.state == "failed"`. Hover on red dot reveals a tooltip with `step`, `error`, `finished_at`. Click on red dot offers "Retry" (calls the targeted refetch endpoint).
- [frontend/src/views/Pipeline.tsx](frontend/src/views/Pipeline.tsx) — pass `last_run` to both `StatusBadge` instances; add a "Refetch Release Notes" action button in the actions area for rows where `release_notes.status ∈ {not_started, not_found}`.
- [frontend/src/components/patches/PatchDetailModal.tsx](frontend/src/components/patches/PatchDetailModal.tsx) — add a "Last run" section per track showing `state`, `started_at`, `finished_at`, `step`, `error` when populated.
- [frontend/src/lib/api.ts](frontend/src/lib/api.ts) — add API client functions for `refetchReleaseNotes(patchId)` and the bulk endpoint.

**Tests.** `cd frontend && npm run build` clean. Manual smoke test in dev: a `not_found` patch shows the badge and a working refetch button; a `failed` `last_run` shows the red dot with hover.

**Done criteria:** UI renders all `last_run` states correctly against real backend data; refetch button triggers a real Zendesk lookup end-to-end.

---

### Unit 9 — UI: side-by-side review view

**Effort:** Medium–Large.
**Depends on:** units 7 + 8.

**Scope.** Review view with two main panels and a toggleable record editor. Triggered when "Approve Docs" is clicked on a `pending_approval` release-notes cell. This view is a **gate in front of** the existing `JiraApprovalModal`, not a replacement for it.

**Two review modes:**

- **Visual comparison** (default) — PDF original on left, DOCX preview on right. The DOCX preview is rendered as PDF on the backend (via `libreoffice --headless`) so both panels show consistent PDF rendering. Quick check that content and layout look right.
- **Content editing** (toggle when needed) — opens the extracted record (items, body blocks, images) as editable fields. Fix missing text, wrong images, reorder blocks. Save → re-render DOCX → preview updates.

**Styling/formatting fixes:** "Open in Word" button links to the local `.docx` file path. Since the app runs locally, this opens directly in Microsoft Word for template-level styling tweaks (indent, font size, image width). Styling fixes go into the template or `render_record()` code once — not per-release manual edits.

Flow:
1. Click "Approve Docs" → `DocsReviewView` opens.
2. PDF on the left (pdf.js or `<embed>`, served by unit 7's endpoint).
3. DOCX preview on the right (rendered as PDF by the backend). Plus "Open in Word" button for the local file path.
4. If content needs fixing → toggle the record editor, edit, save, DOCX re-renders.
5. "Looks good, continue" button → closes the review view and opens the existing `JiraApprovalModal`, pre-filled for the docs ticket. No new Jira UI — reuse what binaries already uses.
6. Jira modal approve → normal approve endpoint → Unit 10's `approved → pdf_exported → published` flow kicks in on the backend.

The review view itself does **not** advance workflow status — `pending_approval → approved` still happens through the Jira modal + approve endpoint, same pattern as binaries.

**Files:**
- `frontend/src/components/patches/DocsReviewView.tsx` (new) — two-panel viewer (PDF left, DOCX-as-PDF right) + toggleable record editor. "Open in Word" button for local file access. Emits a "continue" callback; the parent (Pipeline.tsx) then opens `JiraApprovalModal`.
- [frontend/src/views/Pipeline.tsx](frontend/src/views/Pipeline.tsx) — chain the existing "Approve Docs" path: open `DocsReviewView` first, then on continue open the existing `JiraApprovalModal`. Binaries "Approve" path is untouched.
- `backend/app/api/patches.py` — add `POST /patches/{id}/release-notes/render` endpoint that re-renders DOCX from the record and converts to PDF preview via `libreoffice --headless`.
- *(optional, if `file://` links prove unreliable in the browser)* `backend/app/api/patches.py` — add `POST /patches/{id}/release-notes/reveal` that runs `subprocess.run(["open", "-R", path])`. macOS-only, dev convenience.

**Tests.** `npm run build` clean. Manual smoke test: open the review view on a real `pending_approval` patch, see the PDF render on both sides, toggle record editor, edit a field, see DOCX preview update, click "Open in Word" to verify local file access, click continue, see the Jira modal appear pre-filled, approve, confirm state advances through `approved → pdf_exported → published`.

**Done criteria:** end-to-end docs review workflow works against real Zendesk-fetched release notes.

---

### Unit 10 — DOCX → PDF on approval, attached to Jira docs ticket

**Effort:** Small–Medium.
**Depends on:** unit 9.

**Scope.** Final transition. After a docs cell is approved, convert the approved DOCX to PDF and attach the PDF (not the DOCX) to the docs Jira ticket. State: `approved → pdf_exported → published`. This is the only step where the docs flow differs from binaries.

**Files:**
- `backend/app/pipelines/docs/exporter.py` (new) — `export_docx_to_pdf(docx_path) → pdf_path`. Wrap in lifecycle helper (`step_name="pdf_export"`).
- [backend/app/services/patch_service.py](backend/app/services/patch_service.py) — extend the docs approve flow: after approval, call exporter, advance status to `pdf_exported`, then create Jira ticket and attach the PDF, then advance to `published`.
- Tests against fixtures.

**Tests.**
- Unit: exporter produces a valid PDF from a fixture DOCX.
- Integration: full docs approve flow takes a `pending_approval` cell to `published` with a real Jira ticket key and PDF attachment (against a Jira fixture / mock).
- Two-step save: if Jira fails after `pdf_exported`, the cell remains at `pdf_exported` on disk and can be retried.

**Done criteria:** at least one real docs ticket created in dev with a converted PDF attachment.

---

### Block-to-unit mapping (for cross-reference)

| Block in §2 | Units in §7 |
|---|---|
| Block A — Zendesk fetcher | Unit 3 |
| Block B — DOCX template injection | Units 4 (prototype) + 5 (integrated) |
| Block C — Merge into approval flow | Units 6 (API) + 7 (file serving) + 8 (UI additive) + 9 (review view) + 10 (DOCX→PDF) |
| Foundational (not in §2) | Units 0 (logging) + 1 (state model) + 2 (lifecycle helper) |