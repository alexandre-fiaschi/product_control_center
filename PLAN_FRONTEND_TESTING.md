# Frontend Testing Plan (Deferred)

**Status:** Deferred — backend tests + logging are sufficient for MVP. This plan is saved for when frontend testing is needed.

## Dependencies

```bash
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom msw@latest @playwright/test
npx playwright install chromium
```

## Configuration Files

| File | What |
|------|------|
| `vitest.config.ts` | Separate from vite.config.ts (avoids Tailwind plugin in jsdom). Uses `@vitejs/plugin-react`, jsdom env, `css: false`, globals. |
| `playwright.config.ts` | testDir `./e2e`, Chromium only, webServer starts Vite dev on 5173. |
| `tsconfig.app.json` | Add `"vitest/globals"` to `types` array. |
| `package.json` | Add `"test": "vitest run"`, `"test:watch": "vitest"`, `"test:e2e": "playwright test"` scripts. |

## Test Infrastructure

| File | What |
|------|------|
| `src/test/setup.ts` | jest-dom matchers, cleanup, MSW server lifecycle (beforeAll/afterEach/afterAll). |
| `src/test/test-utils.tsx` | `renderWithProviders()` — wraps with QueryClientProvider (retry: false) + BrowserRouter. Re-exports screen/waitFor/userEvent. |
| `src/test/mocks/data.ts` | Fixture objects: PatchSummary (pending + published), PatchDetail, ProductSummary[], DashboardSummary. |
| `src/test/mocks/handlers.ts` | MSW v2 handlers for all 7 API endpoints. |

## Component Tests (Vitest + React Testing Library)

### StatusBadge
- All 8 statuses render correct label
- Correct colors applied via inline style
- Unknown status falls back to not_started

### API Client
- `request()` returns JSON on 200
- Throws ApiError on 4xx/5xx with status + detail + step
- POST sends body correctly

### PatchDetailModal
- Loading spinner; error state on API fail
- Two-column timeline renders
- Approve button enabled/disabled by status
- onClose on Escape/backdrop; onApprove callback

### JiraApprovalModal
- Header matches pipeline type
- Pre-filled summary/createUpdate
- Description auto-recomputes on releaseName change; stops after manual edit
- Toggle changes button text
- Field modified count; file list renders

### Pipeline View
- Loading skeleton; actionable table renders
- Search/product/status filters work
- History collapsed by default, toggle expands
- Status badge click opens detail modal
- Approve button opens Jira modal

## E2E Tests (Playwright)

| File | Scenarios |
|------|-----------|
| `e2e/scan-flow.spec.ts` | Click Scan, verify toast, verify table updates |
| `e2e/approve-flow.spec.ts` | Open Jira modal, modify fields, submit; toggle "already on portal" |
| `e2e/modal-interactions.spec.ts` | Open/close via click + Escape; detail → approval navigation |
| `e2e/filter-interactions.spec.ts` | Search, product filter, status filter, clear |

## API Mocking Strategy

MSW v2 (`msw/node`) for component tests. Intercepts at network level — no mocking of TanStack Query or api.ts functions. Per-test overrides via `server.use()`.

## Commands

```bash
cd frontend && npm test                    # component tests
cd frontend && npx playwright test         # E2E tests (needs backend on :8000)
```
