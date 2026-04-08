# Jira Integration — Handoff Document

**Date:** 2026-04-03
**Author:** Alexandre Fiaschi (assisted by Claude Code)

---

## What Was Done

### 1. Jira API Token Created & Tested

- Created a **classic API token** (no scopes) at https://id.atlassian.com/manage-profile/security/api-tokens
- Stored in `.env` as `JIRA_API_TOKEN_NO_SCOPES`
- Authentication: **Basic Auth** (email + classic token) against `https://caeglobal.atlassian.net`
- Confirmed working: authenticates as Alexandre Fiaschi (`alexandre.fiaschi@cae.com`)

> **Important:** Scoped API tokens ("Create API token with scopes") were also tested but **do not work** for this Jira instance. The classic token is required. The scoped token is stored in `.env` as `JIRA_API_TOKEN` but should not be used.

### 2. Project Key Confirmed

- Project key: **`CFSSOCP`** (not CFSSOCF as originally documented)
- Project name: `CFS-ServiceOps-CommPortal`
- Project ID: `10008`
- Style: `next-gen`
- URL: https://caeglobal.atlassian.net/jira/software/projects/CFSSOCP/boards/10

### 3. Issue Type Identified

- Issue type for binaries: **"Release notes, documents & binaries"** (id=`10163`)
- This is a project-scoped custom issue type in CFSSOCP
- The same issue type is used for both binaries AND docs (different field values)

### 4. Required Fields Mapped

All required fields for issue type `10163` were discovered via the createmeta API:

| Field | Field ID | Type | Value (Binaries Pipeline) |
|-------|----------|------|---------------------------|
| Project | `project` | project | `{"key": "CFSSOCP"}` |
| Issue Type | `issuetype` | issuetype | `{"id": "10163"}` |
| Summary | `summary` | string | `"Add Release Version v{patch_id}"` |
| Client | `customfield_10328` | array | `[{"value": "Flightscape"}]` |
| Environment | `customfield_10538` | option | `{"value": "All the three"}` |
| Product Name | `customfield_10562` | string | `"CAE® Operations Communication Manager"` |
| Release Name | `customfield_10563` | string | `"Version {major.minor.patch}"` (e.g., "Version 8.1.11") |
| Release Type | `customfield_10616` | option | `{"value": "Version"}` |
| Release Approval | `customfield_10617` | option | `{"value": "Users should not request approval to access or download files on this release"}` |
| Create/Update/Remove | `customfield_10618` | option | `"New CAE Portal Release"` or `"Existing CAE Portal Release"` |

Optional fields used:
- **Description** (`description`): ADF format with template text (see below)
- **Attachment** (`attachment`): Zipped binaries added after ticket creation

### 5. Description Template

```
Hi Team,

I have this binaries for the release {version} that should all be added in a [new/existing] folder '{Release Name}'.

Please contact me for any questions you may have.

Thank you very much,
```

- "new" + "New CAE Portal Release" → first patch creating a new version folder on the portal
- "existing" + "Existing CAE Portal Release" → subsequent patches in a version folder that already exists

### 6. Attachment Workflow

Attachments are added **after** ticket creation, not at creation time:

1. Binaries from the approved patch get zipped as `{patch_id}.zip` (e.g., `8.1.11.0.zip`)
2. **Naming standard:** Always the full patch ID — same format for both new and existing releases
3. Zip is uploaded via `POST /rest/api/3/issue/{ticket_key}/attachments`
4. Requires header: `X-Atlassian-Token: no-check`
5. Content-Type: `multipart/form-data`

### 7. Dry-Run Script Created

`scripts/test_jira.py` — Tests the full flow without creating anything:
- Step 1: Test connection (`GET /myself`)
- Step 2: Validate project key
- Step 3: List issue types and statuses
- Step 4: Fetch create metadata (required/optional fields)
- Step 5: Build sample payload with all real field values
- Step 6: Show attachment API call format

Run: `source venv/bin/activate && python scripts/test_jira.py`

### 8. Dependencies Installed

- `requests` added to venv (used for Jira REST API calls)

---

## What Was Validated (2026-04-03, Session 2)

### 9. Real Test Ticket Created & Verified

- Created ticket **CFSSOCP-6590** for patch 8.1.11.0 via `scripts/create_jira_ticket.py`
- All 10 required fields accepted by Jira — payload format confirmed correct
- Attachment upload confirmed working (test zip uploaded successfully)
- Ticket deleted manually after inspection

### 10. Search API Migration Discovered

- **Old endpoint removed:** `POST /rest/api/3/search` and `GET /rest/api/3/search` both return HTTP 410 (Gone)
- **New endpoint:** `POST /rest/api/3/search/jql` — same request body format, works with classic token
- Migration reference: https://developer.atlassian.com/changelog/#CHANGE-2046

### 11. New/Existing Folder Detection — JQL Corrected

- **Wrong approach:** Searching by summary (`summary ~ "Version {version}"`) — doesn't match existing tickets because summary format varies (e.g., `"Add binaries OpsComm v8.0.27"`)
- **Correct approach:** Search by Release Name custom field: `project = CFSSOCP AND cf[10563] = "Version {version}"`
- Validated against existing ticket CFSSOCP-5824 (Release Name: `8.0.27`, Create/Update: `Existing CAE Portal Release`)

### 12. Existing Ticket Field Observations (CFSSOCP-5824)

Existing tickets in CFSSOCP use different conventions than our new templates:

| Field | Existing (CFSSOCP-5824) | Our New Format |
|-------|------------------------|----------------|
| Summary | `Add binaries OpsComm v8.0.27` | `Add Release Version v8.1.11.0` |
| Release Name | `8.0.27` | `Version 8.1.11` |
| Release Type | `Patch` | `Version` |
| Create/Update | `Existing CAE Portal Release` | Determined by JQL |

> **Decision:** We keep our new format for all new tickets. The old format is just for reference.

### 13. Delete via API Not Available

- `DELETE /rest/api/3/issue/{key}` returns HTTP 403 — account doesn't have delete permission
- Test tickets must be deleted manually from the Jira board

---

## What Needs To Be Done

### Next: Build the Automation

1. **State tracker update** — When a ticket is created, write `jira_ticket_key`, `jira_ticket_url`, and `jira_created_at` fields back to the patch state JSON
2. **Batch processing** — Loop through all `approved` patches and create tickets for each
3. **Status tracking** — Periodically poll ticket status and update the state tracker
4. **Real attachment flow** — Zip actual downloaded binaries (not test files) and attach to tickets

### Configuration Updates Needed

- `config/pipeline.json` — Already contains Jira config, product definitions, and lifecycle

### Known Constraints

- Classic API token expires (check expiration at https://id.atlassian.com/manage-profile/security/api-tokens)
- Token has full account permissions — do not share `.env` or commit it
- The docs pipeline will have different Release Type values (not always "Version") — binaries-specific settings only for now
- CAPTCHA can be triggered after failed login attempts, temporarily blocking API auth

---

## Key Files

| File | Purpose |
|------|---------|
| `.env` | Jira credentials (JIRA_EMAIL, JIRA_API_TOKEN_NO_SCOPES, JIRA_PROJECT_KEY) |
| `scripts/test_jira.py` | Dry-run script — validates connection, fields, payload |
| `scripts/create_jira_ticket.py` | Creates real Jira ticket + attachment for a given patch ID |
| `config/pipeline.json` | Jira form field templates and portal settings |
| `state/patches/*.json` | Patch trackers — will get jira_ticket fields added |

---

## API Reference Quick Sheet

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| Auth test | GET | `/rest/api/3/myself` | |
| Get project | GET | `/rest/api/3/project/CFSSOCP` | |
| Create issue | POST | `/rest/api/3/issue` | Confirmed working |
| Get issue | GET | `/rest/api/3/issue/{key}` | |
| Add attachment | POST | `/rest/api/3/issue/{key}/attachments` | Confirmed working |
| Search (JQL) | POST | `/rest/api/3/search/jql` | **New endpoint** — old `/search` returns 410 |
| Delete issue | DELETE | `/rest/api/3/issue/{key}` | 403 — no permission |
| Get comments | GET | `/rest/api/3/issue/{key}/comment` | |

All endpoints use Basic Auth: `email:classic_api_token` against `https://caeglobal.atlassian.net`.

**JQL for new/existing detection:** `project = CFSSOCP AND cf[10563] = "Version {version}"` (exact match by Release Name field, not summary).

---

## Known Issues & Technical Debt (from code review, 2026-04-08)

### Fixed

- **JQL fuzzy match bug** — The original JQL used `~` (contains) operator: `cf[10563] ~ "{version}"`. Searching for `8.1.1` would also match `8.1.11`, `2.8.1`, `10.8.1`, etc. — causing incorrect new/existing folder classification. **Fixed** to use `=` (exact match) with full Release Name format: `cf[10563] = "Version {version}"`. Tested against live Jira — old query returned 5 false matches, new query returns 0 for `Version 8.1.1` and correctly returns CFSSOCP-6590 for `Version 8.1.11`.

### Open — Will Be Fixed During Backend Build

1. **State model inconsistency** — `test_sftp.py` writes/reads flat `patch['status']` fields, but the committed JSON trackers use nested `binaries.status` and `release_notes.status`. `create_jira_ticket.py` line 111 also referenced `patch_data['status']` (fixed to read nested structure). Both scripts would crash against current state files without the fix. **Resolution:** Extract scripts into proper backend modules with one consistent state model.

2. **State writes not atomic** — `test_sftp.py` overwrites tracker files with plain `json.dump()`. If the process is interrupted mid-write, the file is corrupted and the tracker is lost. ARCHITECTURE.md promises atomic writes (write to `.tmp` → rename) but the scripts don't implement it. **Resolution:** Implement in `backend/app/state/manager.py` during restructure.

3. **Mockup uses hardcoded data** — `product-control-center-mockup.jsx` says "REAL DATA FROM STATE TRACKERS" but hardcodes fake published patches and Jira ticket keys. The real state is 31 pending binaries, 0 published. **Resolution:** The mockup is a design reference only — the real frontend will fetch from the backend API.

4. **Mockup timeline uses fake timestamps** — `PatchDetailModal` uses `patch.discovered_at` for both "Discovered" and "Downloaded" steps, and fabricates release note steps. The actual state has separate per-pipeline timestamps. **Resolution:** Fix when building real `PatchDetailModal.tsx` component.

5. **Mockup description doesn't recompute** — In `JiraApprovalModal`, editing Release Name or Create/Update/Remove doesn't update the description textarea (initialized once on open). **Resolution:** Add `useEffect` to recompute description when those fields change in real component.

6. **Mockup buttons are placeholders** — Scan button, approve buttons, and all links are non-functional (`href="#"`, no handlers). **Resolution:** Expected for a mockup — real handlers built during frontend implementation.
