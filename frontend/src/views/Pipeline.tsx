import { useState, useMemo, useCallback, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Search, Filter, ChevronUp, ChevronDown, ExternalLink, RefreshCw } from "lucide-react";
import { getPatches, getProducts, refetchReleaseNotes } from "../lib/api";
import { dk, formatDate } from "../lib/constants";
import type { PatchSummary, ApproveResponse } from "../lib/types";
import StatusBadge from "../components/shared/StatusBadge";
import Th from "../components/shared/Th";
import Td from "../components/shared/Td";
import PatchDetailModal from "../components/patches/PatchDetailModal";
import JiraApprovalModal from "../components/patches/JiraApprovalModal";

function getLocalPath(productId: string, patchId: string): string {
  return `patches/${productId}/${patchId}`;
}

export default function Pipeline() {
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [productFilter, setProductFilter] = useState(searchParams.get("product") || "all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [showHistory, setShowHistory] = useState(false);

  // Modal state
  const [detailPatch, setDetailPatch] = useState<PatchSummary | null>(null);
  const [approvalModal, setApprovalModal] = useState<{
    patch: PatchSummary;
    pipelineType: "binaries" | "docs";
  } | null>(null);

  const { data: patchList, isLoading: patchesLoading } = useQuery({
    queryKey: ["patches"],
    queryFn: () => getPatches(),
  });

  const { data: products, isLoading: productsLoading } = useQuery({
    queryKey: ["products"],
    queryFn: getProducts,
  });

  const isLoading = patchesLoading || productsLoading;

  const productNames = useMemo(
    () => new Map(products?.map((p) => [p.product_id, p.display_name]) ?? []),
    [products],
  );

  const filteredActionable = useMemo(() => {
    let list = patchList?.actionable ?? [];
    if (productFilter !== "all") list = list.filter((p) => p.product_id === productFilter);
    if (statusFilter === "failed_run") {
      list = list.filter(
        (p) => p.binaries.last_run.state === "failed" || p.release_notes.last_run.state === "failed",
      );
    } else if (statusFilter !== "all") {
      list = list.filter((p) => p.binaries.status === statusFilter || p.release_notes.status === statusFilter);
    }
    if (searchQuery) list = list.filter((p) => p.patch_id.includes(searchQuery) || p.version.includes(searchQuery));
    return list;
  }, [patchList?.actionable, productFilter, statusFilter, searchQuery]);

  const filteredHistory = useMemo(() => {
    let list = patchList?.history ?? [];
    if (productFilter !== "all") list = list.filter((p) => p.product_id === productFilter);
    if (searchQuery) list = list.filter((p) => p.patch_id.includes(searchQuery) || p.version.includes(searchQuery));
    return list;
  }, [patchList?.history, productFilter, searchQuery]);

  // Auto-open modals when navigated from Dashboard with URL params
  useEffect(() => {
    const detailId = searchParams.get("detail");
    const approveId = searchParams.get("approve");
    const pipelineParam = searchParams.get("pipeline") as "binaries" | "docs" | null;
    if (!patchList) return;

    const allPatches = [...patchList.actionable, ...patchList.history];

    if (approveId && pipelineParam) {
      const patch = allPatches.find((p) => p.patch_id === approveId);
      if (patch) setApprovalModal({ patch, pipelineType: pipelineParam });
    } else if (detailId) {
      const patch = allPatches.find((p) => p.patch_id === detailId);
      if (patch) setDetailPatch(patch);
    }
  }, [patchList, searchParams]);

  // Check if a version already has published patches (for new/existing folder logic)
  const isNewFolder = useCallback(
    (patch: PatchSummary): boolean => {
      const allPatches = [...(patchList?.actionable ?? []), ...(patchList?.history ?? [])];
      return !allPatches.some(
        (p) =>
          p.product_id === patch.product_id &&
          p.version === patch.version &&
          p.patch_id !== patch.patch_id &&
          p.binaries.status === "published",
      );
    },
    [patchList],
  );

  // Open Jira approval modal (from table button or from detail modal)
  const openApproval = useCallback(
    (patch: PatchSummary, pipelineType: "binaries" | "docs") => {
      setDetailPatch(null); // close detail if open
      setApprovalModal({ patch, pipelineType });
    },
    [],
  );

  // Trigger a release-notes refetch for a single patch
  const handleRefetchReleaseNotes = useCallback(
    async (patch: PatchSummary) => {
      try {
        const res = await refetchReleaseNotes(patch.product_id, patch.patch_id);
        const msg =
          res.outcome === "converted" ? `Release notes converted (${patch.patch_id})` :
          res.outcome === "downloaded" ? `Release notes downloaded (${patch.patch_id})` :
          res.outcome === "extract_skipped" ? `Downloaded; extraction skipped (${patch.patch_id})` :
          res.outcome === "not_found" ? `No matching release notes on Zendesk (${patch.patch_id})` :
          res.outcome === "already_running" ? `Refetch already in progress (${patch.patch_id})` :
          res.outcome === "not_eligible" ? `Not eligible for refetch (${patch.patch_id})` :
          `Refetch completed: ${res.outcome}`;
        if (res.outcome === "converted" || res.outcome === "downloaded") {
          toast.success(msg);
        } else if (res.outcome === "not_found" || res.outcome === "not_eligible") {
          toast.error(msg);
        } else {
          toast.info(msg);
        }
        queryClient.invalidateQueries({ queryKey: ["patches"] });
        queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Refetch failed";
        toast.error(`Refetch failed: ${msg}`);
      }
    },
    [queryClient],
  );

  // Handle successful approval
  const handleApproveSuccess = useCallback(
    (res: ApproveResponse) => {
      setApprovalModal(null);
      if (res.jira_ticket_key) {
        toast.success(
          `${res.pipeline === "binaries" ? "Binaries" : "Docs"} published — ${res.jira_ticket_key}`,
        );
      } else {
        toast.success(
          `${res.pipeline === "binaries" ? "Binaries" : "Docs"} marked as published`,
        );
      }
      queryClient.invalidateQueries({ queryKey: ["patches"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
    [queryClient],
  );

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        {/* Filter bar skeleton */}
        <div className="rounded-xl p-4 flex items-center gap-4" style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}>
          <div className="w-64 h-8 rounded-lg" style={{ backgroundColor: dk.surface }} />
          <div className="w-32 h-8 rounded-lg" style={{ backgroundColor: dk.surface }} />
          <div className="w-32 h-8 rounded-lg" style={{ backgroundColor: dk.surface }} />
        </div>
        {/* Actionable table skeleton */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: dk.surface }} />
            <div className="w-36 h-5 rounded" style={{ backgroundColor: dk.surface }} />
          </div>
          <div className="rounded-xl p-4" style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}>
            <div className="space-y-4">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="flex items-center gap-4">
                  <div className="w-20 h-4 rounded" style={{ backgroundColor: dk.surface }} />
                  <div className="w-24 h-5 rounded-full" style={{ backgroundColor: dk.surface }} />
                  <div className="w-24 h-5 rounded-full" style={{ backgroundColor: dk.surface }} />
                  <div className="w-32 h-4 rounded" style={{ backgroundColor: dk.surface }} />
                  <div className="ml-auto flex gap-1">
                    <div className="w-20 h-7 rounded-md" style={{ backgroundColor: dk.surface }} />
                    <div className="w-24 h-7 rounded-md" style={{ backgroundColor: dk.surface }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
        {/* History toggle skeleton */}
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded" style={{ backgroundColor: dk.surface }} />
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: dk.surface }} />
          <div className="w-28 h-5 rounded" style={{ backgroundColor: dk.surface }} />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Filter bar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
        padding: 16, borderRadius: 12,
        backgroundColor: dk.card, border: `1px solid ${dk.border}`,
      }}>
        <div style={{ position: "relative", flex: "1 1 0%", maxWidth: 320 }}>
          <Search size={16} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: dk.textDim, pointerEvents: "none" }} />
          <input type="text" placeholder="Search patches..." value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ width: "100%", paddingLeft: 36, paddingRight: 16, paddingTop: 8, paddingBottom: 8, fontSize: 14, borderRadius: 8, backgroundColor: dk.surface, border: `1px solid ${dk.border}`, color: dk.text, outline: "none" }} />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Filter size={14} style={{ color: dk.textDim }} />
          <select value={productFilter} onChange={(e) => setProductFilter(e.target.value)}
            style={{ fontSize: 14, borderRadius: 8, padding: "8px 12px", backgroundColor: dk.surface, border: `1px solid ${dk.border}`, color: dk.text, outline: "none" }}>
            <option value="all">All Products</option>
            {products?.map((p) => (
              <option key={p.product_id} value={p.product_id}>{p.display_name}</option>
            ))}
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
            style={{ fontSize: 14, borderRadius: 8, padding: "8px 12px", backgroundColor: dk.surface, border: `1px solid ${dk.border}`, color: dk.text, outline: "none" }}>
            <option value="all">All Statuses</option>
            <option value="pending_approval">Pending Approval</option>
            <option value="not_started">Not Started</option>
            <option value="not_found">Not Found</option>
            <option value="published">Published</option>
            <option value="failed_run">Failed (last run)</option>
          </select>
        </div>
        <div style={{ marginLeft: "auto", fontSize: 12, color: dk.textDim }}>
          {filteredActionable.length} actionable, {filteredHistory.length} published
        </div>
      </div>

      {/* Actionable table */}
      <div>
        <h2 className="text-base font-semibold mb-3 flex items-center gap-2" style={{ color: dk.text }}>
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: "#f59e0b" }} />
          Actionable ({filteredActionable.length})
        </h2>

        {filteredActionable.length === 0 ? (
          <div
            className="rounded-xl p-10 text-center"
            style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}
          >
            <p className="text-sm" style={{ color: dk.textMute }}>
              {productFilter !== "all" || statusFilter !== "all" || searchQuery
                ? "No actionable patches match your filters."
                : "All patches are published. Run a scan to check for new ones."}
            </p>
          </div>
        ) : (
          <div className="rounded-xl overflow-hidden" style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}>
            <div className="overflow-x-auto">
              <table style={{ width: "100%", fontSize: 14, tableLayout: "fixed" }}>
                <colgroup>
                  <col style={{ width: "14%" }} />
                  <col style={{ width: "18%" }} />
                  <col style={{ width: "18%" }} />
                  <col style={{ width: "20%" }} />
                  <col style={{ width: "30%" }} />
                </colgroup>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${dk.border}` }}>
                    <Th>Patch ID</Th>
                    <Th>Binaries</Th>
                    <Th>Release Notes</Th>
                    <Th>Local Path</Th>
                    <Th>Actions</Th>
                  </tr>
                </thead>
                <tbody>
                  {filteredActionable.map((p) => (
                    <tr key={`${p.product_id}-${p.patch_id}`} style={{ borderBottom: `1px solid ${dk.border}` }}>
                      {/* <Td muted small>{productNames.get(p.product_id) ?? p.product_id}</Td> */}
                      <Td mono bold>{p.patch_id}</Td>
                      <Td>
                        <button className="cursor-pointer" onClick={() => setDetailPatch(p)}>
                          <StatusBadge status={p.binaries.status} lastRun={p.binaries.last_run} />
                        </button>
                      </Td>
                      <Td>
                        <button className="cursor-pointer" onClick={() => setDetailPatch(p)}>
                          <StatusBadge
                            status={p.release_notes.status}
                            lastRun={p.release_notes.last_run}
                            onRetry={() => handleRefetchReleaseNotes(p)}
                          />
                        </button>
                      </Td>
                      <Td mono small>
                        <a
                          href="#"
                          onClick={(e) => e.preventDefault()}
                          className="underline decoration-dotted underline-offset-2"
                          style={{ color: dk.accent }}
                          title={getLocalPath(p.product_id, p.patch_id)}
                        >
                          patches/{p.product_id}/
                        </a>
                      </Td>
                      <Td nowrap>
                        {p.binaries.status !== "published" && (
                          <button
                            disabled={p.binaries.status !== "pending_approval"}
                            onClick={() => p.binaries.status === "pending_approval" && openApproval(p, "binaries")}
                            className="px-2.5 py-1 text-xs font-semibold rounded-md inline-flex items-center gap-1"
                            style={p.binaries.status === "pending_approval"
                              ? { background: "linear-gradient(135deg,#2563eb,#1d4ed8)", color: "#fff" }
                              : { backgroundColor: dk.surface, border: `1px solid ${dk.border}`, color: dk.textDim, opacity: 0.6, cursor: "not-allowed" }}
                            title={
                              p.binaries.status === "pending_approval"
                                ? `Approve binaries for patch ${p.patch_id}.\nOpens the Jira approval form; on submit, a CFSSOCP ticket is created with the binaries .zip attached and the patch is marked Published on the CAE portal.`
                                : `Approve Binaries is disabled — current status: "${p.binaries.status}".\nOnly patches in "Pending Approval" can be approved. Earlier pipeline steps must complete first.`
                            }
                          >
                            Approve Bin
                          </button>
                        )}
                        {p.release_notes.status !== "published" && (
                          p.release_notes.status === "not_started" || p.release_notes.status === "not_found" ? (
                            <button
                              disabled={p.release_notes.last_run.state === "running"}
                              onClick={() => handleRefetchReleaseNotes(p)}
                              className="px-2.5 py-1 text-xs font-semibold rounded-md inline-flex items-center gap-1 ml-1"
                              style={p.release_notes.last_run.state === "running"
                                ? { backgroundColor: dk.surface, border: `1px solid ${dk.border}`, color: dk.textDim, opacity: 0.6, cursor: "not-allowed" }
                                : { background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}
                              title={
                                p.release_notes.last_run.state === "running"
                                  ? `Refetch Docs is disabled — a refetch is already running for patch ${p.patch_id}.\nWait for the current run to finish before retrying.`
                                  : `Fetch release notes for patch ${p.patch_id}.\nRuns the docs pipeline end-to-end: downloads the matching PDF from Zendesk, extracts content via Claude, and renders a CAE-branded DOCX.\n${p.release_notes.status === "not_found" ? "Previous attempt found no matching PDF on Zendesk — click to retry." : "No release-notes run has been attempted yet for this patch."}\nNote: external API calls are gated by docs.enabled / claude.enabled in pipeline.json — both are currently off in dev mode, so this is a no-op.`
                              }
                            >
                              <RefreshCw size={12} /> Refetch Docs
                            </button>
                          ) : (
                            <button
                              disabled={p.release_notes.status !== "pending_approval"}
                              onClick={() => p.release_notes.status === "pending_approval" && openApproval(p, "docs")}
                              className="px-2.5 py-1 text-xs font-semibold rounded-md inline-flex items-center gap-1 ml-1"
                              style={p.release_notes.status === "pending_approval"
                                ? { background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }
                                : { backgroundColor: dk.surface, border: `1px solid ${dk.border}`, color: dk.textDim, opacity: 0.6, cursor: "not-allowed" }}
                              title={
                                p.release_notes.status === "pending_approval"
                                  ? `Approve release notes for patch ${p.patch_id}.\nOpens the Jira approval form; on submit, a CFSSOCP ticket is created with the exported PDF attached and the release notes are marked Published on the CAE portal.`
                                  : `Approve Docs is disabled — current status: "${p.release_notes.status}".\nOnly release notes in "Pending Approval" can be approved. Earlier pipeline steps (download, extract, convert) must complete first.`
                              }
                            >
                              Approve Docs
                            </button>
                          )
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* History table (collapsible) */}
      <div>
        <button
          onClick={() => setShowHistory(!showHistory)}
          className="flex items-center gap-2 text-base font-semibold mb-3 transition-colors"
          style={{ color: dk.text }}
        >
          {showHistory ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: "#34d399" }} />
          History ({filteredHistory.length})
        </button>

        {showHistory && (
          <div className="rounded-xl overflow-hidden" style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm" style={{ minWidth: 900 }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${dk.border}` }}>
                    <Th>Product</Th>
                    <Th>Patch ID</Th>
                    <Th>Binaries</Th>
                    <Th>Jira (Bin)</Th>
                    <Th>Release Notes</Th>
                    <Th>Jira (Docs)</Th>
                    <Th>Published</Th>
                  </tr>
                </thead>
                <tbody>
                  {filteredHistory.map((p) => (
                    <tr
                      key={`${p.product_id}-${p.patch_id}`}
                      className="cursor-pointer"
                      style={{ borderBottom: `1px solid ${dk.border}` }}
                      onClick={() => setDetailPatch(p)}
                    >
                      <Td muted small>{productNames.get(p.product_id) ?? p.product_id}</Td>
                      <Td mono bold>{p.patch_id}</Td>
                      <Td><StatusBadge status="published" /></Td>
                      <Td>
                        {p.binaries.jira_ticket_key ? (
                          <a
                            href={p.binaries.jira_ticket_url ?? "#"}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs flex items-center gap-1"
                            style={{ color: dk.accent }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {p.binaries.jira_ticket_key} <ExternalLink size={10} />
                          </a>
                        ) : (
                          <span style={{ color: dk.textDim }}>{"\u2014"}</span>
                        )}
                      </Td>
                      <Td><StatusBadge status="published" /></Td>
                      <Td>
                        {p.release_notes.jira_ticket_key ? (
                          <a
                            href={p.release_notes.jira_ticket_url ?? "#"}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs flex items-center gap-1"
                            style={{ color: dk.purple }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {p.release_notes.jira_ticket_key} <ExternalLink size={10} />
                          </a>
                        ) : (
                          <span style={{ color: dk.textDim }}>{"\u2014"}</span>
                        )}
                      </Td>
                      <Td muted small>{formatDate(p.binaries.published_at)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* ── Modals ───────────────────────────────────────────────── */}

      {detailPatch && (
        <PatchDetailModal
          patch={detailPatch}
          productName={productNames.get(detailPatch.product_id) ?? detailPatch.product_id}
          onClose={() => setDetailPatch(null)}
          onApprove={openApproval}
        />
      )}

      {approvalModal && (
        <JiraApprovalModal
          patch={approvalModal.patch}
          productName={productNames.get(approvalModal.patch.product_id) ?? approvalModal.patch.product_id}
          pipelineType={approvalModal.pipelineType}
          isNewFolder={isNewFolder(approvalModal.patch)}
          onClose={() => setApprovalModal(null)}
          onSuccess={handleApproveSuccess}
        />
      )}
    </div>
  );
}
