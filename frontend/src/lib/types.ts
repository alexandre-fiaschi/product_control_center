// ─── Patch statuses ─────────────────────────────────────────────────────────

export type PatchStatus =
  | "not_started"
  | "discovered"
  | "downloaded"
  | "converted"
  | "pending_approval"
  | "approved"
  | "pdf_exported"
  | "published";

// ─── Pipeline sub-objects ───────────────────────────────────────────────────

export interface BinariesState {
  status: PatchStatus;
  discovered_at?: string;
  downloaded_at?: string;
  approved_at?: string;
  published_at?: string;
  jira_ticket_key?: string | null;
  jira_ticket_url?: string | null;
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
  docx_path?: string;
  pdf_path?: string;
}

// ─── Patch models ───────────────────────────────────────────────────────────

export interface PatchSummary {
  product_id: string;
  patch_id: string;
  version: string;
  binaries: Pick<BinariesState, "status" | "jira_ticket_key" | "jira_ticket_url" | "published_at">;
  release_notes: Pick<ReleaseNotesState, "status" | "jira_ticket_key" | "jira_ticket_url" | "published_at">;
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
