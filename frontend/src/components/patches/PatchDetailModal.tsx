import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { X, FolderOpen, Box, FileText, ExternalLink, Check, Loader2, AlertCircle } from "lucide-react";
import { getPatchDetail } from "../../lib/api";
import { dk, formatDateTime } from "../../lib/constants";
import type { PatchSummary, PatchDetail, BinariesState, ReleaseNotesState, LastRun } from "../../lib/types";

interface PatchDetailModalProps {
  patch: PatchSummary;
  productName: string;
  onClose: () => void;
  onApprove: (patch: PatchSummary, pipelineType: "binaries" | "docs") => void;
}

// ─── Timeline step ───────────────────────────────────────────────────────────

const TimelineStep = ({
  label,
  timestamp,
  isLast,
  active,
}: {
  label: string;
  timestamp: string | null;
  isLast: boolean;
  active: boolean;
}) => (
  <div className="flex items-start gap-3">
    <div className="flex flex-col items-center">
      <div
        className="w-3 h-3 rounded-full border-2"
        style={{
          borderColor: active ? "#f59e0b" : timestamp ? "#34d399" : dk.borderLt,
          backgroundColor: active
            ? "rgba(245,158,11,0.2)"
            : timestamp
              ? "rgba(52,211,153,0.2)"
              : dk.surface,
        }}
      />
      {!isLast && (
        <div
          className="w-0.5 h-6"
          style={{
            backgroundColor: timestamp ? "rgba(52,211,153,0.3)" : dk.border,
          }}
        />
      )}
    </div>
    <div style={{ marginTop: -2 }}>
      <div
        className="text-sm"
        style={{
          color: active ? "#fbbf24" : timestamp ? dk.text : dk.textDim,
          fontWeight: active ? 600 : 400,
        }}
      >
        {label}
      </div>
      {timestamp && timestamp !== "active" && (
        <div className="text-xs" style={{ color: dk.textDim }}>
          {formatDateTime(timestamp)}
        </div>
      )}
    </div>
  </div>
);

// ─── Last-run section ────────────────────────────────────────────────────────

const LAST_RUN_COLORS: Record<LastRun["state"], string> = {
  idle: dk.textDim,
  running: "#60a5fa",
  success: "#34d399",
  failed: "#f87171",
};

const LAST_RUN_LABELS: Record<LastRun["state"], string> = {
  idle: "Idle",
  running: "Running",
  success: "Succeeded",
  failed: "Failed",
};

function LastRunSection({ lastRun }: { lastRun: LastRun }) {
  const hasRun = lastRun.started_at || lastRun.finished_at;
  const color = LAST_RUN_COLORS[lastRun.state];

  return (
    <div
      className="mt-6 px-3 py-2.5 rounded-lg text-xs"
      style={{ backgroundColor: dk.surface, border: `1px solid ${dk.border}` }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="uppercase tracking-wider font-semibold" style={{ color: dk.textMute }}>
          Last run
        </span>
        <span className="font-semibold" style={{ color }}>
          {LAST_RUN_LABELS[lastRun.state]}
        </span>
        {lastRun.state === "running" && (
          <Loader2 size={12} className="animate-spin" style={{ color }} />
        )}
      </div>
      {!hasRun && lastRun.state === "idle" ? (
        <div style={{ color: dk.textDim }}>No run yet</div>
      ) : (
        <div className="space-y-0.5">
          {lastRun.step && (
            <div style={{ color: dk.text }}>
              <span style={{ color: dk.textMute }}>Step: </span>{lastRun.step}
            </div>
          )}
          {lastRun.started_at && (
            <div style={{ color: dk.textDim }}>
              <span style={{ color: dk.textMute }}>Started: </span>{formatDateTime(lastRun.started_at)}
            </div>
          )}
          {lastRun.finished_at && (
            <div style={{ color: dk.textDim }}>
              <span style={{ color: dk.textMute }}>Finished: </span>{formatDateTime(lastRun.finished_at)}
            </div>
          )}
          {lastRun.error && (
            <div
              className="mt-1 px-2 py-1 rounded font-mono overflow-hidden"
              style={{
                backgroundColor: "rgba(239,68,68,0.08)",
                color: "#fca5a5",
                display: "-webkit-box",
                WebkitLineClamp: 3,
                WebkitBoxOrient: "vertical",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
              title={lastRun.error}
            >
              {lastRun.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function buildBinSteps(b: BinariesState) {
  const raw = [
    { label: "Discovered", ts: b.discovered_at ?? null },
    { label: "Downloaded", ts: b.downloaded_at ?? null },
    {
      label: "Pending Approval",
      ts:
        b.status === "pending_approval"
          ? "active"
          : (b.approved_at ?? b.published_at ?? null),
    },
    { label: "Approved", ts: b.approved_at ?? null },
    { label: "Published", ts: b.published_at ?? null },
  ];
  return raw.filter((s) => s.ts !== null);
}

function buildNoteSteps(rn: ReleaseNotesState) {
  const raw = [
    { label: "Discovered", ts: rn.discovered_at ?? null },
    { label: "Downloaded", ts: rn.downloaded_at ?? null },
    { label: "Converted", ts: rn.converted_at ?? null },
    {
      label: "Pending Approval",
      ts:
        rn.status === "pending_approval"
          ? "active"
          : (rn.approved_at ?? rn.published_at ?? null),
    },
    { label: "Approved", ts: rn.approved_at ?? null },
    { label: "PDF Exported", ts: rn.pdf_exported_at ?? null },
    { label: "Published", ts: rn.published_at ?? null },
  ];
  return raw.filter((s) => s.ts !== null);
}

// ─── Modal ───────────────────────────────────────────────────────────────────

function PatchDetailModal({ patch, productName, onClose, onApprove }: PatchDetailModalProps) {
  const { data: detail, isLoading, isError, error } = useQuery<PatchDetail>({
    queryKey: ["patchDetail", patch.product_id, patch.patch_id],
    queryFn: () => getPatchDetail(patch.product_id, patch.patch_id),
  });

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.7)" }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-xl shadow-2xl"
        style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ────────────────────────────────────────────── */}
        <div className="flex items-start justify-between px-6 pt-5 pb-3">
          <div>
            <div
              className="text-xs font-medium uppercase tracking-wider"
              style={{ color: dk.textMute }}
            >
              {productName} / {patch.version}
            </div>
            <div className="text-lg font-bold mt-0.5" style={{ color: dk.text }}>
              Patch {patch.patch_id}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md hover:opacity-80 transition-opacity"
            style={{ color: dk.textMute }}
          >
            <X size={18} />
          </button>
        </div>

        {/* ── Loading ───────────────────────────────────────────── */}
        {isLoading && (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="animate-spin" size={28} style={{ color: dk.accent }} />
          </div>
        )}

        {/* ── Error ────────────────────────────────────────────── */}
        {isError && (
          <div
            className="mx-6 mb-4 px-4 py-3 rounded-lg flex items-center gap-3"
            style={{ backgroundColor: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.25)" }}
          >
            <AlertCircle size={16} style={{ color: "#f87171" }} />
            <div>
              <div className="text-sm" style={{ color: "#f87171" }}>Failed to load patch details</div>
              <div className="text-xs mt-0.5" style={{ color: dk.textDim }}>
                {(error as any)?.detail || "Unknown error"}
              </div>
            </div>
          </div>
        )}

        {/* ── Loaded content ────────────────────────────────────── */}
        {detail && (
          <>
            {/* Local path bar */}
            <div
              className="mx-6 mb-4 px-3 py-2 rounded-lg flex items-center gap-2 text-sm"
              style={{ backgroundColor: dk.surface }}
            >
              <FolderOpen size={14} style={{ color: dk.textMute, flexShrink: 0 }} />
              <span
                style={{
                  color: dk.accent,
                  textDecoration: "underline",
                  textDecorationStyle: "dotted",
                  textUnderlineOffset: 3,
                }}
              >
                {detail.local_path}/
              </span>
            </div>

            {/* Two-column timeline */}
            <div className="grid grid-cols-2 gap-8" style={{ minHeight: 0, padding: "0 24px 20px", width: "100%" }}>
              {/* ── Binaries column ──────────────────────────────── */}
              <div className="flex flex-col">
                <div className="flex items-center gap-2 mb-6">
                  <Box size={16} style={{ color: dk.accent }} />
                  <span className="font-semibold text-sm" style={{ color: dk.text }}>
                    Binaries
                  </span>
                  {detail.binaries.jira_ticket_url && detail.binaries.jira_ticket_key && (
                    <a
                      href={detail.binaries.jira_ticket_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-xs ml-auto hover:underline"
                      style={{ color: dk.accent }}
                    >
                      {detail.binaries.jira_ticket_key}
                      <ExternalLink size={10} />
                    </a>
                  )}
                </div>

                <div className="flex-1 self-center">
                  {buildBinSteps(detail.binaries).map((step, i, arr) => (
                    <TimelineStep
                      key={step.label}
                      label={step.label}
                      timestamp={step.ts}
                      isLast={i === arr.length - 1}
                      active={step.ts === "active"}
                    />
                  ))}
                </div>

                <LastRunSection lastRun={detail.binaries.last_run} />

                {patch.binaries.status !== "published" && (
                  <button
                    disabled={patch.binaries.status !== "pending_approval"}
                    className="mt-6 w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-opacity"
                    style={patch.binaries.status === "pending_approval"
                      ? { background: "linear-gradient(135deg, #3b82f6, #2563eb)", color: "#fff" }
                      : { backgroundColor: dk.surface, border: `1px solid ${dk.border}`, color: dk.textDim, opacity: 0.6, cursor: "not-allowed" }}
                    onClick={() => patch.binaries.status === "pending_approval" && onApprove(patch, "binaries")}
                  >
                    <Check size={14} />
                    Approve Binaries
                  </button>
                )}
              </div>

              {/* ── Release Notes column ─────────────────────────── */}
              <div className="flex flex-col">
                <div className="flex items-center gap-2 mb-6">
                  <FileText size={16} style={{ color: dk.purple }} />
                  <span className="font-semibold text-sm" style={{ color: dk.text }}>
                    Release Notes
                  </span>
                  {detail.release_notes.jira_ticket_url && detail.release_notes.jira_ticket_key && (
                    <a
                      href={detail.release_notes.jira_ticket_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-xs ml-auto hover:underline"
                      style={{ color: dk.purple }}
                    >
                      {detail.release_notes.jira_ticket_key}
                      <ExternalLink size={10} />
                    </a>
                  )}
                </div>

                <div className="flex-1 self-center">
                  {detail.release_notes.status === "not_started" ? (
                    <div className="text-sm" style={{ color: dk.textDim }}>
                      Not Started
                    </div>
                  ) : detail.release_notes.status === "not_found" ? (
                    <div
                      className="px-3 py-2.5 rounded-lg text-sm"
                      style={{
                        backgroundColor: "rgba(239,68,68,0.08)",
                        border: "1px solid rgba(239,68,68,0.25)",
                        color: "#fca5a5",
                      }}
                    >
                      <div className="font-semibold mb-1">Not Found on Zendesk</div>
                      <div className="text-xs" style={{ color: dk.textMute }}>
                        {detail.release_notes.not_found_reason === "ambiguous_match"
                          ? "Multiple candidate PDFs matched the version — the scraper couldn't pick one safely."
                          : detail.release_notes.not_found_reason === "no_match"
                            ? "No PDF on Zendesk matched the expected title for this patch version."
                            : "The scraper could not locate a matching PDF on Zendesk."}
                      </div>
                      <div className="text-xs mt-2" style={{ color: dk.textDim }}>
                        Use the <span style={{ color: dk.purple, fontWeight: 600 }}>Refetch Docs</span> button in the Pipeline row to retry once a matching PDF is published on Zendesk.
                      </div>
                    </div>
                  ) : (
                    buildNoteSteps(detail.release_notes).map((step, i, arr) => (
                      <TimelineStep
                        key={step.label}
                        label={step.label}
                        timestamp={step.ts}
                        isLast={i === arr.length - 1}
                        active={step.ts === "active"}
                      />
                    ))
                  )}
                </div>

                <LastRunSection lastRun={detail.release_notes.last_run} />

                {patch.release_notes.status !== "published" && (() => {
                  const reviewable =
                    patch.release_notes.status === "converted" ||
                    patch.release_notes.status === "pending_approval";
                  return (
                    <button
                      disabled={!reviewable}
                      className="mt-6 w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-opacity"
                      style={reviewable
                        ? { background: "linear-gradient(135deg, #a78bfa, #7c3aed)", color: "#fff" }
                        : { backgroundColor: dk.surface, border: `1px solid ${dk.border}`, color: dk.textDim, opacity: 0.6, cursor: "not-allowed" }}
                      onClick={() => reviewable && onApprove(patch, "docs")}
                    >
                      <Check size={14} />
                      Review & Approve Release Notes
                    </button>
                  );
                })()}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default PatchDetailModal;
