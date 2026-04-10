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

**Orchestrator changes** ([orchestrator.py](backend/app/services/orchestrator.py)):
- A main scan runs three sequential passes (see section 4.0): SFTP discovery → binaries pass → docs pass.
- The docs pass during a main scan is **strictly first-look only**: it acts on cells where `release_notes.status == not_started` AND `last_run.state != "running"`. It does **not** auto-retry `not_found` cells — those are handled by the manual / targeted refetch endpoint (see section 4.2 for the asymmetry).
- For each per-cell attempt: set `last_run.state = running` + `started_at` at the top, then on success set `state = success` + `finished_at`, on exception set `state = failed` + `finished_at` + `step` + `error`. Workflow status only advances on success.
- Logs cleanly separate the two tracks per patch, using the `subsystem.action.outcome key=value` convention.

**API:**
- Existing `approve` endpoint already supports two-step save and works on a patch. Extend it so the request body can target `binaries` *or* `release_notes` — same contract, different sub-object. This stays one endpoint.
- **Two kinds of scan, two endpoints:**
  - `POST /scan` — **main scan** (SFTP discovery + fan-out to binaries download + docs fetch). Cron/manual trigger. Rejects if another main scan is running.
  - `POST /patches/{id}/release-notes/refetch` — **targeted docs fetch** for one known patch. Does not touch SFTP. Allowed even while a main scan is running, because `last_run.state == "running"` on that specific cell is the lock.
  - `POST /scan/release-notes?version=8.1` — **bulk docs fetch** (loop over N patches). Same locking as targeted.
- New endpoint to serve the source PDF and generated DOCX for the side-by-side UI: `GET /patches/{id}/release-notes/source.pdf` and `.../draft.docx`.

**UI — additive changes to the existing [Pipeline.tsx](frontend/src/views/Pipeline.tsx):**

The current table is already structured right: one row per patch, two status-badge columns (binaries / release notes), two approval buttons. **Workflow status badges stay exactly as they are.** Changes are all additive:

- Add a `not_found` entry to `STATUS_CONFIG` in [frontend/src/lib/constants.ts](frontend/src/lib/constants.ts) so the badge renders with a proper style.
- Add a small **run indicator** next to each workflow badge, driven by `last_run.state`:
  - `idle` or `success` → nothing (don't add visual noise for the happy path)
  - `running` → spinner icon
  - `failed` → red dot, hover reveals a tooltip with `step`, `error`, and `finished_at`; click offers "Retry"
- On rows where `release_notes.status ∈ {not_started, not_found}`, add a "Refetch" action in the existing action area (next to "Approve Docs").
- Extend [PatchDetailModal.tsx](frontend/src/components/patches/PatchDetailModal.tsx) to show the `last_run` details (both tracks) in addition to the existing workflow info.
- When `release_notes.status == pending_approval`, the existing "Approve Docs" path opens a new **side-by-side review view**: source PDF on the left (pdf.js or `<embed>`), generated DOCX on the right. DOCX preview is harder than PDF — for v1, "download to review" is acceptable; HTML render is a v2 nice-to-have.
- Version-header bulk action: "Refetch all missing release notes in V8.1" — calls the bulk docs endpoint.

**Explicitly unchanged:** filter bar, history table, workflow-status badge styles (other than adding `not_found`), approval modal, overall page layout.

**Approval semantics — the only place the two tracks touch:**
- Approving binaries and approving docs are still independent buttons / endpoints / Jira tickets.
- The docs approval has one extra final step the binaries approval doesn't: after approval, generate a final PDF from the approved DOCX and attach *that* to the docs Jira ticket. State: `approved → pdf_exported → published`.

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

## 7. Suggested build order

1. **State model foundation** — add `LastRun` Pydantic model; add `last_run: LastRun` field to both `BinariesState` and `ReleaseNotesState`; add `not_found` to `ReleaseNotesState.status` Literal; add `ScanRecord` model + `state/scans/` storage. Tiny PR, unblocks everything. (Workflow status keeps its current values; no `error` or `failed` values on workflow status — see section 3.)
2. **Orchestrator refactor** — wrap every per-cell attempt (binaries download, docs fetch, converter) in the 5-step lifecycle from section 3.4 (pre-flight lock check → start → execute → success/failure). Existing binaries code gets retrofitted first, then docs blocks build on top of the same helper.
3. **Block A** — extract Zendesk scraper into `backend/app/integrations/zendesk.py`, build `backend/app/pipelines/docs/fetcher.py`, wire into orchestrator behind a feature flag. Tests with fixtures, no live calls in CI.
4. **Block B prototype, standalone** — 3 real PDFs → 3 DOCX outputs. Eyeball the results with Alex. Decide go/no-go on fidelity before continuing.
5. **Block B integrated** — `converter.py` replaces the stub, plugged into the orchestrator after fetcher.
6. **Block C — API** — extend approve endpoint, add `POST /scan` (main, with 409 conflict check), `POST /patches/{id}/release-notes/refetch` (targeted), `POST /scan/release-notes` (bulk), add file-serving endpoints for PDF + DOCX.
7. **Block C — UI** — add `not_found` badge style; add run indicator (spinner / red dot with tooltip) next to each workflow badge; add "Refetch" row action; extend detail modal with `last_run` details; build side-by-side PDF+DOCX review view.
8. **Final step** — DOCX → PDF export on approval, attached to Jira docs ticket.