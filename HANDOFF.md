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

## Known Issues — To Fix During Frontend Build

1. **Mockup uses hardcoded data** — Real state is 31 pending binaries, 0 published. Mockup is design reference only — frontend fetches from API.

2. **Mockup timeline uses fake timestamps** — `PatchDetailModal` fabricates steps. **Fix:** Use real per-pipeline timestamps from API response.

3. **Mockup description doesn't recompute** — Editing Release Name or Create/Update/Remove doesn't update description. **Fix:** Add `useEffect` in `JiraApprovalModal.tsx`.

4. **Mockup buttons are placeholders** — All `href="#"`, no handlers. Expected — real handlers built during Block F4.

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

### Block F1: Scaffold + Shared Code (small)

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

### Block F2: Layout + Dashboard (medium)

App shell with sidebar + view switching, dashboard with summary cards and product cards.

**Files to create:**
```
frontend/src/
├── App.tsx                     # Sidebar + view switching (useState)
├── views/
│   └── Dashboard.tsx           # Summary cards, product cards, quick actionable table
└── components/
    ├── layout/
    │   ├── Sidebar.tsx         # Nav (mockup lines 558–619)
    │   └── Header.tsx          # Scan button + last scan time
    └── shared/
        ├── StatusBadge.tsx     # Status dot + label (mockup lines 79–88)
        ├── SummaryCard.tsx     # Stat card (mockup lines 918–924)
        ├── Th.tsx              # Table header cell
        └── Td.tsx              # Table data cell
```

### Block F3: Pipeline View (medium)

Main working view with filter bar, actionable patch table, collapsible history section.

**Files to create:**
```
frontend/src/
├── views/
│   └── Pipeline.tsx            # Filter bar + actionable/history tables (mockup lines 748–886)
└── components/
    └── patches/
        └── PatchTable.tsx      # Reusable table with status badges + action buttons
```

### Block F4: Modals + Actions (large)

Patch detail timeline and Jira approval modal with full editable form.

**Files to create:**
```
frontend/src/
└── components/
    └── patches/
        ├── PatchDetailModal.tsx    # Timeline view (mockup lines 402–506)
        └── JiraApprovalModal.tsx   # Full Jira form (mockup lines 141–363)
```

### Block F5: Polish (small)

Loading skeletons, error banners, empty states, toast notifications.

### Block F6: Testing (medium)

**Component tests (Vitest + React Testing Library):**
- StatusBadge, PatchTable, JiraApprovalModal, PatchDetailModal, API client

**End-to-end tests (Playwright):**
- Full scan flow, approve with/without Jira, error handling, modal interactions, filter interactions

**Commands:**
```bash
cd frontend && npm test                    # component tests
cd frontend && npx playwright test         # E2E tests
```

---

## Block Summary

| Block | What | Size | Depends on | Status |
|-------|------|------|------------|--------|
| F1 | Scaffold + Shared Code | Small | Backend complete | |
| F2 | Layout + Dashboard | Medium | F1 | |
| F3 | Pipeline View | Medium | F2 | |
| F4 | Modals + Actions | Large | F3 | |
| F5 | Polish | Small | F4 | |
| F6 | Testing | Medium | F5 | |

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
