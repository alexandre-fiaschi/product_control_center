import type {
  DashboardSummary,
  ProductSummary,
  ProductDetail,
  PatchListResponse,
  PatchDetail,
  ScanResponse,
  ApproveResponse,
  JiraApprovalPayload,
  RefetchReleaseNotesResponse,
  BulkRefetchResponse,
} from "./types";

const API_BASE = "/api";

// ─── Error class ────────────────────────────────────────────────────────────

export class ApiError extends Error {
  detail: string;
  step?: string;
  status: number;

  constructor(status: number, body: { detail?: string; step?: string; message?: string }) {
    const msg = body.detail || body.message || "Unknown error";
    super(msg);
    this.name = "ApiError";
    this.status = status;
    this.detail = msg;
    this.step = body.step;
  }
}

// ─── Helpers ────────────────────────────────────────────────────────────────

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const body = await res.json();
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}

// ─── GET endpoints ──────────────────────────────────────────────────────────

export function getDashboardSummary() {
  return request<DashboardSummary>("/dashboard/summary");
}

export function getProducts() {
  return request<ProductSummary[]>("/products");
}

export function getProduct(productId: string) {
  return request<ProductDetail>(`/products/${productId}`);
}

export function getPatches(productId?: string) {
  const path = productId ? `/patches/${productId}` : "/patches";
  return request<PatchListResponse>(path);
}

export function getPatchDetail(productId: string, patchId: string) {
  return request<PatchDetail>(`/patches/${productId}/${patchId}`);
}

// ─── POST endpoints ─────────────────────────────────────────────────────────

export function scanSftp(productId?: string) {
  const path = productId ? `/pipeline/scan/${productId}` : "/pipeline/scan";
  return request<ScanResponse>(path, { method: "POST" });
}

export function approveBinaries(
  productId: string,
  patchId: string,
  fields?: JiraApprovalPayload,
) {
  return request<ApproveResponse>(`/patches/${productId}/${patchId}/binaries/approve`, {
    method: "POST",
    body: fields ? JSON.stringify(fields) : "{}",
  });
}

export function approveDocs(
  productId: string,
  patchId: string,
  fields?: JiraApprovalPayload,
) {
  return request<ApproveResponse>(`/patches/${productId}/${patchId}/docs/approve`, {
    method: "POST",
    body: fields ? JSON.stringify(fields) : "{}",
  });
}

export function refetchReleaseNotes(productId: string, patchId: string) {
  return request<RefetchReleaseNotesResponse>(
    `/patches/${productId}/${patchId}/release-notes/refetch`,
    { method: "POST", body: "{}" },
  );
}

export function refetchReleaseNotesBulk(version?: string) {
  const qs = version ? `?version=${encodeURIComponent(version)}` : "";
  return request<BulkRefetchResponse>(`/pipeline/scan/release-notes${qs}`, {
    method: "POST",
    body: "{}",
  });
}

export function openDocxInWord(productId: string, patchId: string) {
  return request<{ opened: boolean; path: string }>(
    `/patches/${productId}/${patchId}/release-notes/open-in-word`,
    { method: "POST", body: "{}" },
  );
}
