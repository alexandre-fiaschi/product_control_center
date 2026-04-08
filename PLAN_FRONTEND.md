# Frontend Implementation Plan

## Context

The frontend is a **React + Vite** (TypeScript) + Tailwind app that serves as the UI for the OpsComm Pipeline. It's an internal ops tool used by one person (Alex) on localhost. It talks to the FastAPI backend via `/api/*` calls — no direct SFTP, Jira, or file system access.

A fully functional React mockup already exists (`product-control-center-mockup.jsx`, 900 lines) with correct Jira field mappings and complete visual design. This plan turns that mockup into a real app with live API integration.

**Why React + Vite instead of Next.js:**
- Single user on localhost — no SSR, no SEO needed
- The mockup is already pure React — zero rewriting needed
- Vite builds to static files that FastAPI serves directly
- One process, one port, no CORS, no proxy in production

**Deployment:** FastAPI serves both the API (`/api/*`) and the built frontend (static files from `frontend/dist/`) on a single port. In dev, Vite's dev server runs separately with a proxy for hot reload.

**Depends on:** FastAPI backend being built first (10 API endpoints defined in `FRONTEND_WORKFLOWS.md`).

---

## Source Material

| Reference | What it provides |
|-----------|-----------------|
| `product-control-center-mockup.jsx` | Visual design, component structure, theme tokens, Jira modal fields |
| `FRONTEND_WORKFLOWS.md` | API endpoints, JSON response shapes, UI mockups, rendering rules |
| `PLAN_RESTRUCTURE.md` | Folder structure for `frontend/` |
| `config/pipeline.json` | Field options (client, environment, release type, create/update/remove) |

---

## Pages & Views

### 1. Dashboard (`/`)

**API calls:**
- `GET /api/dashboard/summary` — total counts, per-product breakdown
- `GET /api/products` — product list with patch counts

**What it shows:**
- Summary cards: Total Patches, Actionable, Published
- Pie chart: Pending vs Published (recharts)
- Product cards: per-product patch counts, progress bars, bin/docs pending counts
- Quick actionable table: top 5 patches needing attention
- "Scan SFTP" button in header
- Last scan timestamp

**From mockup:** `currentView === "dashboard"` block (lines 643–745), `SummaryCard` component, `productStats` computed data, pie chart.

---

### 2. Pipeline View (`/pipeline`)

**API calls:**
- `GET /api/patches` — all patches (or `GET /api/patches/{product_id}` when filtered)
- Response splits into `actionable[]` and `history[]`

**What it shows:**
- Filter bar: search, product dropdown, status dropdown
- Actionable table: Product, Patch ID, Local Path, Binaries status, Release Notes status, Actions
- History table (collapsed by default): Published patches with Jira ticket links and dates
- "Approve Bin" / "Approve Docs" buttons per row → opens JiraApprovalModal
- Eye icon → opens PatchDetailModal

**From mockup:** `currentView === "pipeline"` block (lines 748–886), filter logic in `filteredActionable`/`filteredHistory`.

---

### 3. Patch Detail Modal

**API call:**
- `GET /api/patches/{product_id}/{patch_id}` — full timeline with all timestamps

**What it shows:**
- Two-column layout: Binaries timeline (left), Release Notes timeline (right)
- Each step shows label + timestamp (or "active" marker for current step)
- Jira ticket link when published
- "Approve Binaries" / "Approve Release Notes" buttons at bottom of each column
- Local path link at top

**From mockup:** `PatchDetailModal` component (lines 402–506), `TimelineStep` subcomponent, `binSteps`/`noteSteps` arrays.

---

### 4. Jira Approval Modal

**API call (on submit):**
- `POST /api/patches/{product_id}/{patch_id}/binaries/approve` — for binaries
- `POST /api/patches/{product_id}/{patch_id}/docs/approve` — for docs
- Request body: all editable field values (summary, client, environment, product name, release name, release type, create/update/remove, description)

**What it shows:**
- Header: blue gradient for binaries, purple for docs
- Context bar: product name, patch ID, local path
- Fixed fields (locked): Project, Issue Type, Release Approval
- Editable fields: Summary, Client, Environment, Product Name, Release Name, Release Type, Create/Update/Remove
- Description textarea (pre-filled with template)
- Attachment preview: `{patch_id}.zip` or `{patch_id}.pdf`
- New/existing folder logic callout (yellow banner)
- "Modified" indicators on changed fields
- Footer: Cancel, Preview JSON Payload, Approve & Create Jira Ticket

**From mockup:** `JiraApprovalModal` component (lines 141–363), `FieldRowStatic`, `EditFieldRow`, `FIELD_OPTIONS`.

---

## Component Breakdown

### Extract from mockup → real components

```
frontend/src/
├── App.tsx                           # Root — sidebar + view switching (useState)
├── main.tsx                          # Entry point, React Query provider
│
├── views/
│   ├── Dashboard.tsx                 # Dashboard view (from mockup lines 643–745)
│   └── Pipeline.tsx                  # Pipeline view (from mockup lines 748–886)
│
├── components/
│   ├── layout/
│   │   ├── Sidebar.tsx               # Sidebar nav (from mockup lines 558–619)
│   │   └── Header.tsx                # Top bar with Scan button + last scan time
│   │
│   ├── patches/
│   │   ├── StatusBadge.tsx           # Status dot + label (from mockup lines 79–88)
│   │   ├── PatchTable.tsx            # Reusable table for actionable + history
│   │   ├── PatchDetailModal.tsx      # Timeline view (from mockup lines 402–506)
│   │   └── JiraApprovalModal.tsx     # Full Jira form (from mockup lines 141–363)
│   │
│   └── shared/
│       ├── SummaryCard.tsx           # Stat card (from mockup lines 918–924)
│       ├── Th.tsx                    # Table header cell (from mockup lines 904–909)
│       └── Td.tsx                    # Table data cell (from mockup lines 911–916)
│
└── lib/
    ├── api.ts                        # Typed fetch wrapper
    ├── types.ts                      # TypeScript types
    └── constants.ts                  # Theme tokens + status config
```

**No file-based routing.** Views switch via `useState` in `App.tsx` (same pattern as the mockup's `currentView`). Two views, not enough pages to justify a router.

---

## Shared Constants (`lib/constants.ts`)

Extract directly from mockup:

```
dk (theme tokens)        → lines 92–105
STATUS_CONFIG            → lines 59–68
FIELD_OPTIONS            → lines 109–114
inputStyle / selectStyle → lines 118–137
```

These are used across multiple components and should live in one place.

---

## API Client (`lib/api.ts`)

Typed wrapper around `fetch`. All calls go through this.

```typescript
const API_BASE = "/api";  // same origin in prod, proxied to localhost:8000 by vite in dev

// GET helpers
getDashboardSummary()                          → GET /api/dashboard/summary
getProducts()                                  → GET /api/products
getProduct(productId)                          → GET /api/products/{product_id}
getPatches(productId?)                         → GET /api/patches or /api/patches/{product_id}
getPatchDetail(productId, patchId)             → GET /api/patches/{product_id}/{patch_id}

// POST helpers
scanSftp(productId?)                           → POST /api/pipeline/scan or /scan/{product_id}
approveBinaries(productId, patchId, fields)    → POST /api/patches/{product_id}/{patch_id}/binaries/approve
approveDocs(productId, patchId, fields)        → POST /api/patches/{product_id}/{patch_id}/docs/approve
```

Each function returns typed responses matching the shapes in `FRONTEND_WORKFLOWS.md`.

---

## TypeScript Types (`lib/types.ts`)

Derived from `FRONTEND_WORKFLOWS.md` response shapes:

```typescript
// Core
PatchStatus       — "not_started" | "discovered" | "downloaded" | "converted" | "pending_approval" | "approved" | "pdf_exported" | "published"
BinariesState     — { status, discovered_at?, downloaded_at?, approved_at?, published_at?, jira_ticket_key?, jira_ticket_url? }
ReleaseNotesState — { status, discovered_at?, downloaded_at?, converted_at?, approved_at?, pdf_exported_at?, published_at?, jira_ticket_key?, jira_ticket_url? }
PatchSummary      — { product_id, patch_id, version, binaries, release_notes }
PatchDetail       — PatchSummary + { sftp_folder, sftp_path, local_path, binaries.files?, release_notes.docx_path?, release_notes.pdf_path? }

// Dashboard
DashboardSummary  — { total_patches, binaries: {counts}, release_notes: {counts}, by_product[], last_scan }
ProductSummary    — { product_id, display_name, last_scanned_at, counts, total_patches }
ProductDetail     — ProductSummary + { versions: { [version]: { patch_count } } }

// Responses
PatchListResponse — { actionable: PatchSummary[], history: PatchSummary[] }
ScanResponse      — { scanned_at, products_scanned[], new_patches[], total_new }
ApproveResponse   — { patch_id, pipeline, status, jira_ticket_key?, jira_ticket_url?, error?, note? }

// Jira form
JiraApprovalPayload — { summary, client, environment, product_name, release_name, release_type, create_update_remove, description }
```

---

## Data Flow

```
User clicks "Scan SFTP"
  → POST /api/pipeline/scan
  → Toast: "2 new patches found" or "No new patches"
  → Refetch dashboard + patch list

User clicks "Approve Bin" on a patch row
  → JiraApprovalModal opens (pre-filled with defaults from pipeline.json)
  → User reviews/edits fields
  → User clicks "Approve & Create Jira Ticket"
  → POST /api/patches/{product_id}/{patch_id}/binaries/approve
  → On success: toast with Jira link, row updates to "published"
  → On error: toast with error, button changes to "Retry"

User clicks eye icon on a patch
  → GET /api/patches/{product_id}/{patch_id}
  → PatchDetailModal opens with full timeline
  → Can approve from within the modal too
```

---

## State Management

No global state library needed. Use:

- **React Query (TanStack Query)** or **SWR** for server state (API data, caching, refetching)
- **`useState`** for local UI state (modals, filters, search)
- Refetch patch list after scan or approve actions via query invalidation

---

## Loading, Error & Empty States

The mockup has none of these. The real app needs:

| State | Where | Behavior |
|-------|-------|----------|
| Loading | Dashboard, Pipeline | Skeleton cards / table rows |
| Loading | Scan button | Spinner + "Scanning..." text, button disabled |
| Loading | Approve button | Spinner + "Creating ticket..." text |
| Error | Scan | Red toast: "Scan failed: {error}" |
| Error | Approve | Red toast: error message, Approve button → Retry |
| Error | API unreachable | Banner: "Cannot connect to backend" |
| Empty | Pipeline (no actionable) | "All patches are published" message |
| Empty | Dashboard (no patches) | "No patches found. Run a scan to discover patches." |
| Success | Scan with results | Green toast: "Scan complete — N new patches found" |
| Success | Approve | Green toast with clickable Jira ticket link |

---

## Error Handling & User Feedback

### API error responses

The backend returns structured errors. The frontend must display them clearly:

```json
{
  "error": "Jira ticket creation failed",
  "detail": "401 Unauthorized — API token may have expired",
  "patch_id": "8.1.12.0",
  "pipeline": "binaries",
  "step": "jira_create"
}
```

### Error display by operation

**Scan SFTP:**
- Button shows spinner + "Scanning..." while running
- Success: green toast "Scan complete — 2 new patches found" (auto-dismiss 5s)
- Success (0 new): blue toast "No new patches found"
- SFTP error: red toast "SFTP scan failed: Connection timed out" (stays until dismissed)
- Partial failure: yellow toast "Scanned 2/3 products — ACARS_V8_0 failed: {error}"

**Approve (binaries or docs):**
- Modal submit button shows spinner + "Creating Jira ticket..."
- Modal stays open during request (don't close on click)
- Success: close modal → green toast with clickable Jira link "CFSSOCP-1234 created" → row updates
- Jira auth error (401): red toast "Jira authentication failed — API token may have expired. Check backend .env"
- Jira field error (400): red toast showing Jira's error message (e.g., "Release Name is required")
- Network error: red toast "Cannot reach backend — is uvicorn running?"
- On error: modal stays open so user can retry without re-entering fields

**Page load (dashboard, pipeline):**
- Loading: skeleton cards / skeleton table rows
- API unreachable: full-page error banner "Cannot connect to backend at localhost:8000" with retry button
- Empty data: contextual message "No patches found. Run a scan to discover patches."

### Error toast design

```
┌─ ✕ ─────────────────────────────────────────────┐
│  ⚠ Jira ticket creation failed                  │
│                                                   │
│  401 Unauthorized — API token may have expired   │
│  Patch: 8.1.12.0 · Step: jira_create            │
│                                                   │
│  [ Retry ]                              [ Dismiss ]│
└──────────────────────────────────────────────────┘
```

- Red background for errors, green for success, blue for info
- Error toasts stay until dismissed (don't auto-dismiss)
- Success toasts auto-dismiss after 5 seconds
- Include patch ID and step so it's immediately clear what failed
- Retry button on error toasts re-triggers the action

### API client error handling (`lib/api.ts`)

```typescript
// Every API call goes through this
async function apiCall<T>(url: string, options?: RequestInit): Promise<T> {
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      const error = await res.json();
      throw new ApiError(error.error, error.detail, error.step, res.status);
    }
    return res.json();
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError("Network error", "Cannot reach backend — is uvicorn running?", "fetch", 0);
  }
}
```

Custom `ApiError` class carries structured error info from backend → displayed in toasts.

### React Query error handling

```typescript
// Global error handler for all queries
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,                    // retry once on failure
      staleTime: 30_000,           // 30s before refetch
      onError: (err) => {
        toast.error(err.message);  // show in toast
      },
    },
    mutations: {
      retry: 0,                    // don't auto-retry mutations (scan, approve)
      onError: (err) => {
        toast.error(err.message);
      },
    },
  },
});
```

---

## Frontend Logging

The frontend doesn't write log files, but it needs visible logging in the browser console for debugging:

### Console logging
- `console.info` — API calls: `[API] GET /api/patches → 200 (34 patches)`
- `console.info` — Actions: `[ACTION] Approve binaries for ACARS_V8_1/8.1.12.0`
- `console.error` — Failures: `[ERROR] POST /api/patches/.../approve → 401: {detail}`
- `console.warn` — Unexpected states: `[WARN] Patch 8.1.12.0 has status "approved" but no jira_ticket_key`

### Activity log panel (stretch goal)
Optional: a collapsible log panel at the bottom of the screen showing recent actions and their results — like a mini terminal. Useful for seeing what happened during a scan or batch approve. Not needed for MVP but worth considering for Phase 5.

---

## Vite Config (`vite.config.ts`)

Dev proxy so the Vite dev server forwards `/api/*` to FastAPI:

```typescript
export default defineConfig({
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
```

Only needed during development (hot reload). In production, FastAPI serves everything on one port — no proxy.

---

## Dependencies

```
react, react-dom                — framework
typescript, @types/react        — types
vite, @vitejs/plugin-react      — build tool
tailwindcss, postcss            — styling
lucide-react                    — icons (already used in mockup)
recharts                        — pie chart (already used in mockup)
@tanstack/react-query           — server state / data fetching
sonner (or react-hot-toast)     — toast notifications
```

---

## Implementation Order

### Phase 1: Shell + Static UI
1. Scaffold React app (`npm create vite@latest frontend -- --template react-ts`)
2. Install Tailwind, lucide-react, recharts, @tanstack/react-query, sonner
3. Create `lib/constants.ts` — extract `dk`, `STATUS_CONFIG`, `FIELD_OPTIONS` from mockup
4. Create `lib/types.ts` — TypeScript types from FRONTEND_WORKFLOWS.md response shapes
5. Create `lib/api.ts` — typed fetch wrapper (returns mock data initially)
6. Build `App.tsx` with `Sidebar.tsx` + `Header.tsx` + view switching
7. Build `StatusBadge.tsx`, `SummaryCard.tsx`, `Th.tsx`, `Td.tsx`

### Phase 2: Dashboard
7. Build Dashboard page (`/`) — summary cards, pie chart, product cards, quick actionable table
8. Wire to `lib/api.ts` with React Query

### Phase 3: Pipeline View
9. Build Pipeline page (`/pipeline`) — filter bar, actionable table, history table
10. Build `PatchTable.tsx` — shared table component used by both views

### Phase 4: Modals
11. Build `PatchDetailModal.tsx` — timeline view with approve buttons
12. Build `JiraApprovalModal.tsx` — full Jira form with editable fields
13. Wire approve actions → POST to backend → toast → refetch

### Phase 5: Polish
14. Add loading skeletons, error banners, empty states
15. Add toast notifications (scan results, approve success/error)
16. Test full flow: scan → view patches → approve → see Jira link
17. Responsive tweaks (not critical — internal tool on a Mac)

---

## What the backend must provide

The frontend assumes these 10 endpoints exist and return the exact shapes from `FRONTEND_WORKFLOWS.md`:

| Priority | Endpoint | Needed for |
|----------|----------|------------|
| 1 | `GET /api/dashboard/summary` | Dashboard page |
| 1 | `GET /api/patches` | Pipeline view |
| 1 | `GET /api/patches/{product_id}` | Pipeline view (filtered) |
| 2 | `GET /api/products` | Dashboard product cards |
| 2 | `GET /api/patches/{product_id}/{patch_id}` | Patch detail modal |
| 3 | `POST /api/pipeline/scan` | Scan button |
| 3 | `POST /api/pipeline/scan/{product_id}` | Scan single product |
| 3 | `POST /api/patches/.../binaries/approve` | Approve binaries |
| 3 | `POST /api/patches/.../docs/approve` | Approve docs |
| 4 | `GET /api/products/{product_id}` | Product detail (future) |

Priority 1-2 endpoints are needed for the UI to render anything. Priority 3 are needed for actions. Priority 4 can wait.

---

## Testing

### Manual test checklist

Since this is an internal tool for one user, the priority is manual end-to-end testing over automated tests. Run through this checklist after each major change:

**Dashboard:**
- [ ] Page loads with real data from backend
- [ ] Summary cards show correct counts matching state files
- [ ] Pie chart renders Pending vs Published
- [ ] Product cards show correct per-product counts
- [ ] Clicking a product card navigates to pipeline with that product filtered
- [ ] "Scan SFTP" button shows spinner, then toast with result

**Pipeline view:**
- [ ] Actionable table shows patches that aren't fully published
- [ ] History table (collapsed) shows fully published patches
- [ ] Search filters by patch ID
- [ ] Product dropdown filters correctly
- [ ] Status dropdown filters correctly
- [ ] "Approve Bin" button opens JiraApprovalModal with blue header
- [ ] "Approve Docs" button opens JiraApprovalModal with purple header
- [ ] Eye icon opens PatchDetailModal

**JiraApprovalModal:**
- [ ] All fields pre-filled with correct defaults
- [ ] New/existing folder logic correct (yellow banner message)
- [ ] Editing a field shows "modified" indicator
- [ ] Submit shows spinner, modal stays open
- [ ] On success: modal closes, toast with Jira link, row updates to published
- [ ] On error: modal stays open, red toast with error detail, can retry

**PatchDetailModal:**
- [ ] Both timelines render with correct steps and timestamps
- [ ] Published patches show Jira ticket links
- [ ] Pending patches show approve buttons
- [ ] Approving from modal opens JiraApprovalModal

**Error scenarios:**
- [ ] Stop backend → frontend shows "Cannot connect to backend" banner
- [ ] Start backend → banner disappears, data loads
- [ ] Trigger Jira 401 → toast shows "API token may have expired"
- [ ] Scan with SFTP unreachable → toast shows SFTP error detail

### Automated tests (if needed later)

```
frontend/src/__tests__/
├── api.test.ts                 # API client error handling, ApiError class
├── StatusBadge.test.tsx        # Renders correct color/label for each status
├── JiraApprovalModal.test.tsx  # Field defaults, new/existing logic, modified tracking
└── PatchTable.test.tsx         # Filters, sorting, empty states
```

Dependencies: `vitest` + `@testing-library/react` (comes with create-next-app).
Not required for MVP — add when the app stabilizes.
