// ─── Patch statuses ─────────────────────────────────────────────────────────

export type PatchStatus =
  | "not_started"
  | "discovered"
  | "downloaded"
  | "extracted"
  | "converted"
  | "pending_approval"
  | "approved"
  | "pdf_exported"
  | "published"
  | "not_found";

// ─── Last run (execution state, orthogonal to workflow status) ──────────────

export type LastRunState = "idle" | "running" | "success" | "failed";

export interface LastRun {
  state: LastRunState;
  started_at: string | null;
  finished_at: string | null;
  step: string | null;
  error: string | null;
}

// ─── Pipeline sub-objects ───────────────────────────────────────────────────

export interface BinariesState {
  status: PatchStatus;
  discovered_at?: string;
  downloaded_at?: string;
  approved_at?: string;
  published_at?: string;
  jira_ticket_key?: string | null;
  jira_ticket_url?: string | null;
  last_run: LastRun;
  files?: string[];
}

export interface ReleaseNotesState {
  status: PatchStatus;
  discovered_at?: string;
  downloaded_at?: string;
  converted_at?: string;
  approved_at?: string;
  pdf_exported_at?: string;
  published_at?: string;
  jira_ticket_key?: string | null;
  jira_ticket_url?: string | null;
  not_found_reason?: "no_match" | "ambiguous_match" | null;
  last_run: LastRun;
  docx_path?: string;
  pdf_path?: string;
}

// ─── Patch models ───────────────────────────────────────────────────────────

export interface PatchSummary {
  product_id: string;
  patch_id: string;
  version: string;
  binaries: Pick<BinariesState, "status" | "jira_ticket_key" | "jira_ticket_url" | "published_at" | "last_run">;
  release_notes: Pick<ReleaseNotesState, "status" | "jira_ticket_key" | "jira_ticket_url" | "published_at" | "last_run">;
}

export interface PatchDetail {
  product_id: string;
  patch_id: string;
  version: string;
  sftp_folder: string;
  sftp_path: string;
  local_path: string;
  binaries: BinariesState;
  release_notes: ReleaseNotesState;
}

// ─── Dashboard ──────────────────────────────────────────────────────────────

export interface DashboardSummary {
  total_patches: number;
  binaries: {
    pending_approval: number;
    approved: number;
    published: number;
  };
  release_notes: {
    not_started: number;
    pending_approval: number;
    published: number;
  };
  by_product: ProductBreakdown[];
  last_scan: string | null;
}

export interface ProductBreakdown {
  product_id: string;
  display_name: string;
  actionable: number;
  published: number;
  total: number;
}

// ─── Products ───────────────────────────────────────────────────────────────

export interface ProductSummary {
  product_id: string;
  display_name: string;
  last_scanned_at: string | null;
  counts: {
    binaries: { pending_approval: number; published: number };
    release_notes: { not_started: number; pending_approval: number; published: number };
  };
  total_patches: number;
}

export interface ProductDetail extends ProductSummary {
  versions: Record<string, { patch_count: number }>;
}

// ─── API responses ──────────────────────────────────────────────────────────

export interface PatchListResponse {
  product_id?: string;
  actionable: PatchSummary[];
  history: PatchSummary[];
}

export interface ScanResponse {
  scanned_at: string;
  products_scanned: string[];
  new_patches: {
    product_id: string;
    patch_id: string;
    binaries_status: string;
    release_notes_status: string;
  }[];
  total_new: number;
}

export interface ApproveResponse {
  patch_id: string;
  pipeline: "binaries" | "docs";
  status: string;
  jira_ticket_key?: string;
  jira_ticket_url?: string;
  error?: string;
  note?: string;
}

// ─── Refetch responses ──────────────────────────────────────────────────────

export type RefetchOutcome =
  | "converted"
  | "downloaded"
  | "extract_skipped"
  | "not_found"
  | "already_running"
  | "not_eligible"
  | "failed"
  | "error";

export interface RefetchReleaseNotesResponse {
  outcome: RefetchOutcome;
  product_id: string;
  patch_id: string;
  release_notes_status: PatchStatus;
  last_run: LastRun;
  scan_id: string;
}

export interface BulkRefetchResult {
  product_id: string;
  patch_id: string;
  outcome: RefetchOutcome;
  release_notes_status: PatchStatus;
}

export interface BulkRefetchResponse {
  scan_id: string;
  version_filter: string;
  attempted: number;
  results: BulkRefetchResult[];
  counts: {
    attempted: number;
    downloaded: number;
    not_found: number;
    converted: number;
    extract_skipped: number;
    not_eligible: number;
    already_running: number;
    failed: number;
  };
}

// ─── Jira approval form ─────────────────────────────────────────────────────

export interface JiraApprovalPayload {
  summary: string;
  client: string;
  environment: string;
  product_name: string;
  release_name: string;
  release_type: string;
  create_update_remove: string;
  description: string;
}
