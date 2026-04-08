import { useState, useEffect, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  X,
  Zap,
  Package,
  Layers,
  FolderOpen,
  Paperclip,
  AlertCircle,
  Check,
  CheckCircle2,
  Loader2,
  File,
} from "lucide-react";
import { toast } from "sonner";
import type { PatchSummary, JiraApprovalPayload } from "../../lib/types";
import { getPatchDetail } from "../../lib/api";
import { dk, FIELD_OPTIONS, inputStyle, selectStyle } from "../../lib/constants";

// ─── Props ──────────────────────────────────────────────────────────────────

interface JiraApprovalModalProps {
  patch: PatchSummary;
  productName: string;
  pipelineType: "binaries" | "docs";
  isNewFolder: boolean;
  onClose: () => void;
  onSuccess: (res: any) => void;
}

// ─── Inline sub-components ──────────────────────────────────────────────────

const FieldRowStatic = ({
  label,
  value,
  sublabel,
  fieldId,
  locked,
  small,
}: {
  label: string;
  value: string;
  sublabel?: string;
  fieldId?: string;
  locked?: boolean;
  small?: boolean;
}) => (
  <div
    className="flex items-start px-4 py-3 gap-4"
    style={{
      backgroundColor: dk.surface,
      borderBottom: `1px solid ${dk.border}`,
    }}
  >
    <div className="w-48 flex-shrink-0">
      <div
        className="text-sm font-medium flex items-center gap-1.5"
        style={{ color: dk.textMute }}
      >
        {label}
        {locked && (
          <svg
            width="10"
            height="10"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#5c5e68"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        )}
      </div>
      {fieldId && (
        <div className="text-xs font-mono" style={{ color: dk.textDim }}>
          {fieldId}
        </div>
      )}
    </div>
    <div className="flex-1 min-w-0">
      <div className={small ? "text-xs" : "text-sm"} style={{ color: dk.textDim }}>
        {value}
      </div>
      {sublabel && (
        <div className="text-xs mt-0.5" style={{ color: dk.textDim }}>
          {sublabel}
        </div>
      )}
    </div>
  </div>
);

const EditFieldRow = ({
  label,
  fieldId,
  touched,
  children,
}: {
  label: string;
  fieldId?: string;
  touched?: boolean;
  highlight?: boolean;
  children: React.ReactNode;
}) => (
  <div
    className="flex items-center px-4 py-3 gap-4"
    style={{
      backgroundColor: dk.surface,
      borderBottom: `1px solid ${dk.border}`,
    }}
  >
    <div className="w-48 flex-shrink-0">
      <div
        className="text-sm font-medium flex items-center gap-1.5"
        style={{ color: touched ? dk.accent : dk.textMute }}
      >
        {label}
        {touched && (
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: dk.accent, display: "inline-block" }}
          />
        )}
      </div>
      {fieldId && (
        <div className="text-xs font-mono" style={{ color: dk.textDim }}>
          {fieldId}
        </div>
      )}
    </div>
    <div className="flex-1 min-w-0">{children}</div>
  </div>
);

// ─── Focus ring class ───────────────────────────────────────────────────────

const inputFocusRing = "focus:ring-2 focus:ring-blue-500 focus:border-transparent";

// ─── Main component ─────────────────────────────────────────────────────────

export default function JiraApprovalModal({
  patch,
  productName: productNameProp,
  pipelineType,
  isNewFolder,
  onClose,
  onSuccess,
}: JiraApprovalModalProps) {
  // Fetch patch detail for file list
  const { data: detail } = useQuery({
    queryKey: ["patchDetail", patch.product_id, patch.patch_id],
    queryFn: () => getPatchDetail(patch.product_id, patch.patch_id),
  });
  const files = detail?.binaries.files ?? [];

  // Editable fields
  const [summary, setSummary] = useState(
    pipelineType === "binaries"
      ? `Add Release Version ${patch.patch_id}`
      : `Add Release notes ${patch.patch_id}`,
  );
  const [client, setClient] = useState("Flightscape");
  const [environment, setEnvironment] = useState("All the three");
  const [productName, setProductName] = useState(
    "CAE\u00ae Operations Communication Manager",
  );
  const [releaseName, setReleaseName] = useState(`Version ${patch.version}`);
  const [releaseType, setReleaseType] = useState("Version");
  const [createUpdate, setCreateUpdate] = useState(
    isNewFolder ? "New CAE Portal Release" : "Existing CAE Portal Release",
  );
  const [description, setDescription] = useState("");
  const [alreadyOnPortal, setAlreadyOnPortal] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [submitting, setSubmitting] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [submitError, setSubmitError] = useState<string | null>(null);

  const markTouched = useCallback((field: string) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
  }, []);

  const touchedCount = Object.values(touched).filter(Boolean).length;

  // ─── Description auto-recompute ─────────────────────────────────────────

  useEffect(() => {
    if (touched.description) return;
    const newOrExisting = createUpdate.includes("New") ? "new" : "existing";
    setDescription(
      `Hi Team,\n\nI have this ${pipelineType} for the release ${patch.version} that should be added in a ${newOrExisting} folder '${releaseName}'.\n\nPlease contact me for any questions you may have.\n\nThank you very much,`,
    );
  }, [releaseName, createUpdate, pipelineType, touched.description, patch.version]);

  // ─── Escape key ─────────────────────────────────────────────────────────

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  // ─── Submit ─────────────────────────────────────────────────────────────

  const handleSubmit = async () => {
    // DEV MODE: show payload as toast instead of calling API
    const payload: JiraApprovalPayload = {
      summary,
      client,
      environment,
      product_name: productName,
      release_name: releaseName,
      release_type: releaseType,
      create_update_remove: createUpdate,
      description,
    };

    const label = pipelineType === "binaries" ? "Binaries" : "Docs";
    const endpoint = `POST /api/patches/${patch.product_id}/${patch.patch_id}/${pipelineType === "binaries" ? "binaries" : "docs"}/approve`;

    if (alreadyOnPortal) {
      toast.info(
        `[DRY RUN] ${label} — Mark as Published\n\n${endpoint}\nBody: {} (empty — skip Jira)`,
        { duration: 5000 },
      );
    } else {
      toast.info(
        `[DRY RUN] ${label} — Create Jira Ticket\n\n${endpoint}\n\n${JSON.stringify(payload, null, 2)}`,
        { duration: 5000 },
      );
    }

    console.info(`[DRY RUN] ${endpoint}`, alreadyOnPortal ? {} : payload);
    onClose();
  };

  // ─── Gradient colors ───────────────────────────────────────────────────

  const isBinaries = pipelineType === "binaries";
  const headerGradient = isBinaries
    ? "linear-gradient(135deg,#2563eb,#1d4ed8)"
    : "linear-gradient(135deg,#7c3aed,#6d28d9)";
  const accentColor = isBinaries ? dk.accent : dk.purple;

  // ─── Render ─────────────────────────────────────────────────────────────

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backgroundColor: "rgba(0,0,0,0.7)" }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-xl shadow-2xl"
        style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}
      >
        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div
          className="flex items-center justify-between px-6 py-4"
          style={{ background: headerGradient }}
        >
          <div className="flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-full flex items-center justify-center"
              style={{ backgroundColor: "rgba(255,255,255,0.15)" }}
            >
              <Zap size={18} color="white" />
            </div>
            <div>
              <div className="text-xs font-medium" style={{ color: "rgba(255,255,255,0.6)" }}>
                CFSSOCP &mdash; Create Issue
              </div>
              <div className="text-lg font-bold text-white">
                {isBinaries ? "Binaries" : "Release Notes"} Approval
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-white/10 transition-colors"
          >
            <X size={20} color="white" />
          </button>
        </div>

        {/* ── Context bar ────────────────────────────────────────────────── */}
        <div
          className="flex items-center gap-6 px-6 py-3 text-sm"
          style={{
            backgroundColor: "rgba(79,143,247,0.06)",
            borderBottom: `1px solid ${dk.border}`,
          }}
        >
          <div className="flex items-center gap-1.5">
            <Package size={14} style={{ color: dk.textMute }} />
            <span style={{ color: dk.textMute }}>Product:</span>
            <span style={{ color: dk.text }}>{productNameProp}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Layers size={14} style={{ color: dk.textMute }} />
            <span style={{ color: dk.textMute }}>Patch:</span>
            <span className="font-mono" style={{ color: dk.text }}>
              {patch.patch_id}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <FolderOpen size={14} style={{ color: dk.textMute }} />
            <span style={{ color: dk.textMute }}>Local:</span>
            <span
              className="font-mono"
              style={{
                color: dk.accent,
                textDecoration: "underline",
                textDecorationStyle: "dotted",
              }}
            >
              patches/{patch.product_id}/{patch.patch_id}/
            </span>
          </div>
        </div>

        {/* ── Body ───────────────────────────────────────────────────────── */}
        <div className="px-6 py-5 space-y-5">
          {/* 1. Issue Details — fixed fields */}
          <div>
            <div className="text-sm font-semibold mb-2" style={{ color: dk.text }}>
              Issue Details{" "}
              <span style={{ color: dk.textDim, fontWeight: 400 }}>&mdash; fixed</span>
            </div>
            <div className="rounded-lg overflow-hidden" style={{ border: `1px solid ${dk.border}` }}>
              <FieldRowStatic
                label="Project"
                value="CFSSOCP"
                sublabel="CFS-ServiceOps-CommPortal"
                locked
              />
              <FieldRowStatic
                label="Issue Type"
                value="Release notes, documents & binaries"
                sublabel="ID: 10163"
                locked
              />
              <FieldRowStatic
                label="Release Approval"
                value="Users should not request approval to access or download files on this release"
                fieldId="customfield_10617"
                locked
                small
              />
            </div>
          </div>

          {/* 2. Editable Fields */}
          <div>
            <div className="text-sm font-semibold mb-2" style={{ color: dk.text }}>
              Editable Fields{" "}
              <span style={{ color: accentColor, fontWeight: 400 }}>
                &mdash; modify before submitting
              </span>
            </div>
            <div className="rounded-lg overflow-hidden" style={{ border: `1px solid ${dk.border}` }}>
              {/* Create/Update/Remove */}
              <EditFieldRow
                label="Create/Update/Remove"
                fieldId="customfield_10618"
                touched={touched.createUpdate}
                highlight
              >
                <select
                  value={createUpdate}
                  onChange={(e) => {
                    markTouched("createUpdate");
                    setCreateUpdate(e.target.value);
                  }}
                  className={inputFocusRing}
                  style={{
                    ...selectStyle,
                    color: dk.accent,
                    fontWeight: 600,
                  }}
                >
                  {FIELD_OPTIONS.createUpdateRemove.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </EditFieldRow>

              {/* Summary */}
              <EditFieldRow
                label="Summary"
                fieldId="summary"
                touched={touched.summary}
              >
                <input
                  type="text"
                  value={summary}
                  onChange={(e) => {
                    markTouched("summary");
                    setSummary(e.target.value);
                  }}
                  className={`font-mono ${inputFocusRing}`}
                  style={inputStyle}
                />
              </EditFieldRow>

              {/* Client */}
              <EditFieldRow
                label="Client"
                fieldId="customfield_10328"
                touched={touched.client}
              >
                <select
                  value={client}
                  onChange={(e) => {
                    markTouched("client");
                    setClient(e.target.value);
                  }}
                  className={inputFocusRing}
                  style={selectStyle}
                >
                  {FIELD_OPTIONS.client.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </EditFieldRow>

              {/* Environment */}
              <EditFieldRow
                label="Environment"
                fieldId="customfield_10538"
                touched={touched.environment}
              >
                <select
                  value={environment}
                  onChange={(e) => {
                    markTouched("environment");
                    setEnvironment(e.target.value);
                  }}
                  className={inputFocusRing}
                  style={selectStyle}
                >
                  {FIELD_OPTIONS.environment.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </EditFieldRow>

              {/* Product Name */}
              <EditFieldRow
                label="Product Name"
                fieldId="customfield_10562"
                touched={touched.productName}
              >
                <input
                  type="text"
                  value={productName}
                  onChange={(e) => {
                    markTouched("productName");
                    setProductName(e.target.value);
                  }}
                  className={inputFocusRing}
                  style={inputStyle}
                />
              </EditFieldRow>

              {/* Release Name */}
              <EditFieldRow
                label="Release Name"
                fieldId="customfield_10563"
                touched={touched.releaseName}
                highlight
              >
                <input
                  type="text"
                  value={releaseName}
                  onChange={(e) => {
                    markTouched("releaseName");
                    setReleaseName(e.target.value);
                  }}
                  className={inputFocusRing}
                  style={{
                    ...inputStyle,
                    color: dk.accent,
                    fontWeight: 600,
                  }}
                />
              </EditFieldRow>

              {/* Release Type */}
              <EditFieldRow
                label="Release Type"
                fieldId="customfield_10616"
                touched={touched.releaseType}
              >
                <select
                  value={releaseType}
                  onChange={(e) => {
                    markTouched("releaseType");
                    setReleaseType(e.target.value);
                  }}
                  className={inputFocusRing}
                  style={selectStyle}
                >
                  {FIELD_OPTIONS.releaseType.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </EditFieldRow>
            </div>
          </div>

          {/* 3. Description */}
          <div>
            <div className="text-sm font-semibold mb-2 flex items-center gap-2" style={{ color: dk.text }}>
              Description
              {touched.description && (
                <span
                  className="text-xs px-1.5 py-0.5 rounded"
                  style={{
                    backgroundColor: "rgba(251,191,36,0.15)",
                    color: "#fbbf24",
                  }}
                >
                  modified
                </span>
              )}
            </div>
            <textarea
              rows={7}
              value={description}
              onChange={(e) => {
                markTouched("description");
                setDescription(e.target.value);
              }}
              className={inputFocusRing}
              style={{
                ...inputStyle,
                minHeight: 140,
                resize: "vertical",
              }}
            />
          </div>

          {/* 4. Attachment */}
          <div>
            <div className="text-sm font-semibold mb-2" style={{ color: dk.text }}>
              Attachment
            </div>
            <div
              className="flex items-center gap-3 px-4 py-3 rounded-lg"
              style={{
                backgroundColor: dk.surface,
                border: `1px solid ${dk.border}`,
              }}
            >
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
                style={{
                  backgroundColor: isBinaries
                    ? "rgba(79,143,247,0.15)"
                    : "rgba(167,139,250,0.15)",
                }}
              >
                <Paperclip size={14} style={{ color: accentColor }} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium" style={{ color: dk.text }}>
                  {patch.patch_id}.{isBinaries ? "zip" : "pdf"}
                </div>
                <div className="text-xs" style={{ color: dk.textDim }}>
                  {isBinaries
                    ? "Zipped binaries from patch folder"
                    : "PDF exported from CAE-branded .docx template"}
                </div>
              </div>
              <div className="text-xs font-mono flex-shrink-0" style={{ color: dk.textDim }}>
                POST /rest/api/3/issue/&#123;key&#125;/attachments
              </div>
            </div>
            {files.length > 0 && (
              <div
                className="mt-2 rounded-lg px-4 py-2.5"
                style={{ backgroundColor: dk.surface, border: `1px solid ${dk.border}` }}
              >
                <div className="text-xs font-medium mb-1.5" style={{ color: dk.textDim }}>
                  Contents ({files.length} file{files.length !== 1 ? "s" : ""})
                </div>
                <div className="space-y-1">
                  {files.map((f) => (
                    <div key={f} className="flex items-center gap-2 text-xs font-mono" style={{ color: dk.textMute }}>
                      <File size={11} style={{ color: dk.textDim, flexShrink: 0 }} />
                      {f}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* 5. Logic callout */}
          <div
            className="flex items-start gap-3 px-4 py-3 rounded-lg"
            style={{
              backgroundColor: "rgba(251,191,36,0.06)",
              border: "1px solid rgba(251,191,36,0.2)",
            }}
          >
            <AlertCircle
              size={16}
              className="flex-shrink-0 mt-0.5"
              style={{ color: "#fbbf24" }}
            />
            <div className="text-xs leading-relaxed" style={{ color: dk.textMute }}>
              <strong style={{ color: "#fbbf24" }}>New/Existing logic:</strong> JQL checks{" "}
              <code className="font-mono" style={{ color: dk.textDim }}>
                project = CFSSOCP AND cf[10563] = &quot;Version {patch.version}&quot;
              </code>
              .{" "}
              {isNewFolder
                ? "No existing ticket found \u2014 defaulting to \"New CAE Portal Release\"."
                : "Existing ticket found \u2014 defaulting to \"Existing CAE Portal Release\"."}
            </div>
          </div>
        </div>

        {/* ── Footer ─────────────────────────────────────────────────────── */}
        <div
          className="px-6 py-4 space-y-3"
          style={{
            backgroundColor: dk.surface,
            borderTop: `1px solid ${dk.border}`,
          }}
        >
          {/* Row 1: Toggle + modified count */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setAlreadyOnPortal((v) => !v)}
                className="relative w-11 h-6 rounded-full transition-colors"
                style={{
                  backgroundColor: alreadyOnPortal ? "#22c55e" : dk.border,
                }}
              >
                <span
                  className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform"
                  style={{
                    transform: alreadyOnPortal ? "translateX(20px)" : "translateX(0)",
                  }}
                />
              </button>
              <div>
                <div className="text-sm font-medium" style={{ color: dk.text }}>
                  Already available on portal
                </div>
                <div className="text-xs" style={{ color: dk.textDim }}>
                  {alreadyOnPortal
                    ? "Skip Jira ticket \u2014 mark as approved & published immediately"
                    : "Turn on if this release is already live on the community portal"}
                </div>
              </div>
            </div>
            {touchedCount > 0 && (
              <span
                className="text-xs px-2 py-1 rounded-full font-medium"
                style={{
                  backgroundColor: "rgba(251,191,36,0.15)",
                  color: "#fbbf24",
                }}
              >
                {touchedCount} field(s) modified
              </span>
            )}
          </div>

          {/* Submit error */}
          {submitError && (
            <div
              className="text-sm px-3 py-2 rounded-lg flex items-center gap-2"
              style={{
                backgroundColor: "rgba(239,68,68,0.1)",
                border: "1px solid rgba(239,68,68,0.3)",
                color: "#f87171",
              }}
            >
              <AlertCircle size={14} />
              {submitError}
            </div>
          )}

          {/* Row 2: Action buttons */}
          <div className="flex items-center justify-between">
            <button
              onClick={onClose}
              className="text-sm px-4 py-2 rounded-lg hover:bg-white/5 transition-colors"
              style={{ color: dk.textMute }}
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold text-white transition-opacity disabled:opacity-60"
              style={{
                background: alreadyOnPortal
                  ? "linear-gradient(135deg,#22c55e,#16a34a)"
                  : isBinaries
                    ? "linear-gradient(135deg,#2563eb,#1d4ed8)"
                    : "linear-gradient(135deg,#7c3aed,#6d28d9)",
              }}
            >
              {submitting ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  {alreadyOnPortal ? "Publishing..." : "Creating ticket..."}
                </>
              ) : alreadyOnPortal ? (
                <>
                  <CheckCircle2 size={16} />
                  Mark as Approved &amp; Published
                </>
              ) : (
                <>
                  <Check size={16} />
                  Approve &amp; Create Jira Ticket
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
