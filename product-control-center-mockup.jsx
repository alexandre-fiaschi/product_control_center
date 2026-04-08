import { useState, useMemo } from "react";
import {
  Package, FileText, ChevronDown, ChevronRight, X, Check, Clock, Upload,
  Search, Filter, RefreshCw, LayoutDashboard, FolderOpen, Settings,
  ExternalLink, Paperclip, AlertCircle, CheckCircle2, Circle, ArrowRight,
  ChevronUp, Eye, Layers, Activity, Box, Zap
} from "lucide-react";
// recharts removed — no longer needed for dashboard

// ─── REAL DATA FROM STATE TRACKERS ───────────────────────────────────────────

const PRODUCTS = [
  { product_id: "ACARS_V8_1", display_name: "ACARS V8.1", total: 24, structure: "hierarchical" },
  { product_id: "ACARS_V8_0", display_name: "ACARS V8.0", total: 5, structure: "hierarchical" },
  { product_id: "ACARS_V7_3", display_name: "ACARS V7.3", total: 5, structure: "flat" },
];

// Local path convention: patches/{PRODUCT_ID}/{PATCH_ID}/
const getLocalPath = (productId, patchId) => `patches/${productId}/${patchId}`;


const PATCHES = [
  // V8.1 — actionable
  { product_id: "ACARS_V8_1", version: "8.1.12", patch_id: "8.1.12.0", binaries: { status: "pending_approval" }, release_notes: { status: "pending_approval" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.12", patch_id: "8.1.12.1", binaries: { status: "pending_approval" }, release_notes: { status: "not_started" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.11", patch_id: "8.1.11.0", binaries: { status: "pending_approval" }, release_notes: { status: "pending_approval" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.11", patch_id: "8.1.11.1", binaries: { status: "pending_approval" }, release_notes: { status: "pending_approval" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.10", patch_id: "8.1.10.0", binaries: { status: "pending_approval" }, release_notes: { status: "not_started" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.10", patch_id: "8.1.10.1", binaries: { status: "pending_approval" }, release_notes: { status: "pending_approval" }, discovered_at: "2026-04-03T17:01:11Z" },
  // V8.1 — published history
  { product_id: "ACARS_V8_1", version: "8.1.9", patch_id: "8.1.9.0", binaries: { status: "published", jira_ticket_key: "CFSSOCP-6401", published_at: "2026-03-15T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-6402", published_at: "2026-03-16T09:00:00Z" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.9", patch_id: "8.1.9.1", binaries: { status: "published", jira_ticket_key: "CFSSOCP-6403", published_at: "2026-03-17T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-6404", published_at: "2026-03-18T09:00:00Z" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.8", patch_id: "8.1.8.0", binaries: { status: "published", jira_ticket_key: "CFSSOCP-6380", published_at: "2026-03-10T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-6381", published_at: "2026-03-11T09:00:00Z" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.7", patch_id: "8.1.7.0", binaries: { status: "published", jira_ticket_key: "CFSSOCP-6350", published_at: "2026-03-01T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-6351", published_at: "2026-03-02T09:00:00Z" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.5", patch_id: "8.1.5.0", binaries: { status: "published", jira_ticket_key: "CFSSOCP-6300", published_at: "2026-02-20T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-6301", published_at: "2026-02-21T09:00:00Z" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.4", patch_id: "8.1.4.0", binaries: { status: "published", jira_ticket_key: "CFSSOCP-6280", published_at: "2026-02-15T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-6281", published_at: "2026-02-16T09:00:00Z" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.3", patch_id: "8.1.3.0", binaries: { status: "published", jira_ticket_key: "CFSSOCP-6260", published_at: "2026-02-10T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-6261", published_at: "2026-02-11T09:00:00Z" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.1", patch_id: "8.1.1.0", binaries: { status: "published", jira_ticket_key: "CFSSOCP-6240", published_at: "2026-02-05T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-6241", published_at: "2026-02-06T09:00:00Z" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.0", patch_id: "8.1.0.0", binaries: { status: "published", jira_ticket_key: "CFSSOCP-6200", published_at: "2026-01-20T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-6201", published_at: "2026-01-21T09:00:00Z" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.0", patch_id: "8.1.0.1", binaries: { status: "published", jira_ticket_key: "CFSSOCP-6202", published_at: "2026-01-22T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-6203", published_at: "2026-01-23T09:00:00Z" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.0", patch_id: "8.1.0.2", binaries: { status: "published", jira_ticket_key: "CFSSOCP-6204", published_at: "2026-01-24T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-6205", published_at: "2026-01-25T09:00:00Z" }, discovered_at: "2026-04-03T17:01:11Z" },
  { product_id: "ACARS_V8_1", version: "8.1.0", patch_id: "8.1.0.3", binaries: { status: "published", jira_ticket_key: "CFSSOCP-6206", published_at: "2026-01-26T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-6207", published_at: "2026-01-27T09:00:00Z" }, discovered_at: "2026-04-03T17:01:11Z" },
  // V8.0
  { product_id: "ACARS_V8_0", version: "8.0.30", patch_id: "8.0.30.0", binaries: { status: "pending_approval" }, release_notes: { status: "not_started" }, discovered_at: "2026-04-03T17:04:36Z" },
  { product_id: "ACARS_V8_0", version: "8.0.29", patch_id: "8.0.29.0", binaries: { status: "pending_approval" }, release_notes: { status: "not_started" }, discovered_at: "2026-04-03T17:04:36Z" },
  { product_id: "ACARS_V8_0", version: "8.0.28", patch_id: "8.0.28.0", binaries: { status: "published", jira_ticket_key: "CFSSOCP-5824", published_at: "2026-03-01T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-5825", published_at: "2026-03-02T10:00:00Z" }, discovered_at: "2026-04-03T17:04:36Z" },
  { product_id: "ACARS_V8_0", version: "8.0.28", patch_id: "8.0.28.1", binaries: { status: "published", jira_ticket_key: "CFSSOCP-5830", published_at: "2026-03-05T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-5831", published_at: "2026-03-06T10:00:00Z" }, discovered_at: "2026-04-03T17:04:36Z" },
  { product_id: "ACARS_V8_0", version: "8.0.29", patch_id: "8.0.29.1", binaries: { status: "pending_approval" }, release_notes: { status: "pending_approval" }, discovered_at: "2026-04-03T17:04:36Z" },
  // V7.3 — all published
  { product_id: "ACARS_V7_3", version: "7.3.27", patch_id: "7.3.27.0", binaries: { status: "published", jira_ticket_key: "CFSSOCP-5700", published_at: "2026-02-10T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-5701", published_at: "2026-02-11T10:00:00Z" }, discovered_at: "2026-04-03T17:04:36Z" },
  { product_id: "ACARS_V7_3", version: "7.3.27", patch_id: "7.3.27.1", binaries: { status: "published", jira_ticket_key: "CFSSOCP-5710", published_at: "2026-02-15T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-5711", published_at: "2026-02-16T10:00:00Z" }, discovered_at: "2026-04-03T17:04:36Z" },
  { product_id: "ACARS_V7_3", version: "7.3.27", patch_id: "7.3.27.5", binaries: { status: "published", jira_ticket_key: "CFSSOCP-5720", published_at: "2026-02-20T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-5721", published_at: "2026-02-21T10:00:00Z" }, discovered_at: "2026-04-03T17:04:36Z" },
  { product_id: "ACARS_V7_3", version: "7.3.27", patch_id: "7.3.27.7", binaries: { status: "published", jira_ticket_key: "CFSSOCP-5730", published_at: "2026-02-25T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-5731", published_at: "2026-02-26T10:00:00Z" }, discovered_at: "2026-04-03T17:04:36Z" },
  { product_id: "ACARS_V7_3", version: "7.3.27", patch_id: "7.3.27.8", binaries: { status: "published", jira_ticket_key: "CFSSOCP-5740", published_at: "2026-03-01T10:00:00Z" }, release_notes: { status: "published", jira_ticket_key: "CFSSOCP-5741", published_at: "2026-03-02T10:00:00Z" }, discovered_at: "2026-04-03T17:04:36Z" },
];

// ─── HELPERS ────────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  not_started:       { label: "Not Started",       bg: "rgba(107,114,128,0.15)", text: "#9ca3af", dot: "#6b7280" },
  discovered:        { label: "Discovered",        bg: "rgba(96,165,250,0.15)",  text: "#93c5fd", dot: "#60a5fa" },
  downloaded:        { label: "Downloaded",        bg: "rgba(129,140,248,0.15)", text: "#a5b4fc", dot: "#818cf8" },
  pending_approval:  { label: "Pending Approval",  bg: "rgba(251,191,36,0.15)",  text: "#fbbf24", dot: "#f59e0b" },
  approved:          { label: "Approved",          bg: "rgba(34,211,238,0.15)",  text: "#67e8f9", dot: "#22d3ee" },
  converted:         { label: "Converted",         bg: "rgba(192,132,252,0.15)", text: "#c4b5fd", dot: "#a78bfa" },
  pdf_exported:      { label: "PDF Exported",      bg: "rgba(45,212,191,0.15)",  text: "#5eead4", dot: "#2dd4bf" },
  published:         { label: "Published",         bg: "rgba(52,211,153,0.12)",  text: "#6ee7b7", dot: "#34d399" },
};

const formatDate = (iso) => {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};
const formatDateTime = (iso) => {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

const StatusBadge = ({ status }) => {
  const c = STATUS_CONFIG[status] || STATUS_CONFIG.not_started;
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap"
      style={{ backgroundColor: c.bg, color: c.text }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: c.dot }} />
      {c.label}
    </span>
  );
};

// ─── DARK THEME TOKENS ──────────────────────────────────────────────────────

const dk = {
  bg:       "#0f1117",
  surface:  "#181a20",
  card:     "#1e2028",
  border:   "#2a2d37",
  borderLt: "#33363f",
  text:     "#e4e5e9",
  textMute: "#8b8d97",
  textDim:  "#5c5e68",
  accent:   "#4f8ff7",
  accentHv: "#3b7ce5",
  purple:   "#a78bfa",
  purpleHv: "#8b5cf6",
};

// ─── FIELD OPTIONS (from pipeline.json) ─────────────────────────────────────

const FIELD_OPTIONS = {
  client: ["Flightscape", "CAE", "Other"],
  environment: ["All the three", "Production", "Staging", "Development"],
  releaseType: ["Version", "Update", "Patch", "Sub Component"],
  createUpdateRemove: ["New CAE Portal Release", "Existing CAE Portal Release", "Remove CAE Portal Release"],
};

// ─── SHARED INPUT STYLES ────────────────────────────────────────────────────

const inputStyle = {
  backgroundColor: "rgba(255,255,255,0.04)",
  border: `1px solid rgba(255,255,255,0.1)`,
  borderRadius: 6,
  color: "#e4e5e9",
  fontSize: 14,
  padding: "6px 10px",
  width: "100%",
  outline: "none",
};
const inputFocusRing = "focus:ring-2 focus:ring-blue-500 focus:border-transparent";
const selectStyle = {
  ...inputStyle,
  appearance: "none",
  backgroundImage: `url("data:image/svg+xml,%3Csvg width='12' height='8' viewBox='0 0 12 8' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1.5L6 6.5L11 1.5' stroke='%238b8d97' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")`,
  backgroundRepeat: "no-repeat",
  backgroundPosition: "right 10px center",
  paddingRight: 32,
  cursor: "pointer",
};

// ─── JIRA APPROVAL MODAL (dark, editable) ───────────────────────────────────

const JiraApprovalModal = ({ patch, onClose, pipelineType }) => {
  if (!patch) return null;
  const version = patch.version;
  const isNewFolder = !PATCHES.some(
    (p) => p.product_id === patch.product_id && p.version === version && p.patch_id !== patch.patch_id && p.binaries.status === "published"
  );
  const product = PRODUCTS.find((p) => p.product_id === patch.product_id);
  const isPurple = pipelineType === "docs";

  // ── Editable field state ──
  const [summary, setSummary] = useState(
    pipelineType === "binaries" ? `Add Release Version ${patch.patch_id}` : `Add Release notes ${patch.patch_id}`
  );
  const [client, setClient] = useState("Flightscape");
  const [environment, setEnvironment] = useState("All the three");
  const [productName, setProductName] = useState("CAE\u00ae Operations Communication Manager");
  const [releaseName, setReleaseName] = useState(`Version ${version}`);
  const [releaseType, setReleaseType] = useState("Version");
  const [createUpdate, setCreateUpdate] = useState(
    isNewFolder ? "New CAE Portal Release" : "Existing CAE Portal Release"
  );
  const newOrExisting = createUpdate.includes("New") ? "new" : "existing";
  const [description, setDescription] = useState(
    `Hi Team,\n\nI have this ${pipelineType} for the release ${version} that should be added in a ${newOrExisting} folder '${releaseName}'.\n\nPlease contact me for any questions you may have.\n\nThank you very much,`
  );

  // Already on portal toggle — skip Jira, auto-approve+publish
  const [alreadyOnPortal, setAlreadyOnPortal] = useState(false);

  // Track if user modified fields (visual indicator)
  const [touched, setTouched] = useState({});
  const markTouched = (field) => setTouched((prev) => ({ ...prev, [field]: true }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ backgroundColor: "rgba(0,0,0,0.7)" }}>
      <div className="w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-xl shadow-2xl" style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}>
        {/* Header */}
        <div className="rounded-t-xl px-6 py-4 flex items-center justify-between"
          style={{ background: isPurple ? "linear-gradient(135deg,#7c3aed,#6d28d9)" : "linear-gradient(135deg,#2563eb,#1d4ed8)" }}>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded flex items-center justify-center" style={{ backgroundColor: "rgba(255,255,255,0.2)" }}>
              <Zap size={18} className="text-white" />
            </div>
            <div>
              <div className="text-white text-sm font-medium" style={{ opacity: 0.75 }}>CFSSOCP — Create Issue</div>
              <div className="text-white text-lg font-semibold">
                {isPurple ? "Release Notes" : "Binaries"} Approval
              </div>
            </div>
          </div>
          <button onClick={onClose} className="text-white rounded-lg p-1.5 transition-colors">
            <X size={20} />
          </button>
        </div>

        {/* Context bar */}
        <div className="px-6 py-3 flex items-center gap-6 text-sm flex-wrap" style={{ backgroundColor: "rgba(79,143,247,0.06)", borderBottom: `1px solid ${dk.border}` }}>
          <div className="flex items-center gap-2">
            <Package size={14} style={{ color: dk.accent }} />
            <span style={{ color: dk.textMute }}>Product:</span>
            <span className="font-medium" style={{ color: dk.text }}>{product?.display_name}</span>
          </div>
          <div className="flex items-center gap-2">
            <Layers size={14} style={{ color: dk.accent }} />
            <span style={{ color: dk.textMute }}>Patch:</span>
            <span className="font-mono font-medium" style={{ color: dk.text }}>{patch.patch_id}</span>
          </div>
          <div className="flex items-center gap-2">
            <FolderOpen size={14} style={{ color: dk.accent }} />
            <span style={{ color: dk.textMute }}>Local:</span>
            <a href="#" onClick={(e) => e.preventDefault()} className="font-mono text-xs underline decoration-dotted underline-offset-2"
              style={{ color: dk.accent }} title={`Open ${getLocalPath(patch.product_id, patch.patch_id)}`}>
              {getLocalPath(patch.product_id, patch.patch_id)}/
            </a>
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-5">
          {/* Issue Details — fixed fields */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: dk.textDim }}>Issue Details
              <span className="ml-2 normal-case tracking-normal font-normal" style={{ color: dk.textDim, opacity: 0.6 }}>— fixed</span>
            </h3>
            <div className="rounded-lg overflow-hidden" style={{ border: `1px solid ${dk.border}` }}>
              <FieldRowStatic label="Project" value="CFSSOCP" sublabel="CFS-ServiceOps-CommPortal" locked />
              <FieldRowStatic label="Issue Type" value="Release notes, documents & binaries" sublabel="ID: 10163" locked />
              <FieldRowStatic label="Release Approval" value="Users should not request approval to access or download files on this release" fieldId="customfield_10617" locked small />
            </div>
          </div>

          {/* Editable Fields */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: dk.textDim }}>Editable Fields
              <span className="ml-2 normal-case tracking-normal font-normal" style={{ color: dk.accent, opacity: 0.8 }}>— modify before submitting</span>
            </h3>
            <div className="rounded-lg overflow-hidden" style={{ border: `1px solid ${dk.border}` }}>
              {/* Create / Update / Remove — dropdown (highlighted, FIRST) */}
              <EditFieldRow label="Create / Update / Remove" fieldId="customfield_10618" touched={touched.createUpdate} highlight>
                <select value={createUpdate} onChange={(e) => { setCreateUpdate(e.target.value); markTouched("createUpdate"); }}
                  className={inputFocusRing} style={{ ...selectStyle, color: "#60a5fa", fontWeight: 600 }}>
                  {FIELD_OPTIONS.createUpdateRemove.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </EditFieldRow>

              {/* Summary — text input */}
              <EditFieldRow label="Summary" fieldId="summary" touched={touched.summary}>
                <input type="text" value={summary} onChange={(e) => { setSummary(e.target.value); markTouched("summary"); }}
                  className={inputFocusRing} style={{ ...inputStyle, fontFamily: "monospace" }} />
              </EditFieldRow>

              {/* Client — dropdown */}
              <EditFieldRow label="Client" fieldId="customfield_10328" touched={touched.client}>
                <select value={client} onChange={(e) => { setClient(e.target.value); markTouched("client"); }}
                  className={inputFocusRing} style={selectStyle}>
                  {FIELD_OPTIONS.client.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </EditFieldRow>

              {/* Environment — dropdown */}
              <EditFieldRow label="Environment" fieldId="customfield_10538" touched={touched.environment}>
                <select value={environment} onChange={(e) => { setEnvironment(e.target.value); markTouched("environment"); }}
                  className={inputFocusRing} style={selectStyle}>
                  {FIELD_OPTIONS.environment.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </EditFieldRow>

              {/* Product Name — text input */}
              <EditFieldRow label="Product Name" fieldId="customfield_10562" touched={touched.productName}>
                <input type="text" value={productName} onChange={(e) => { setProductName(e.target.value); markTouched("productName"); }}
                  className={inputFocusRing} style={inputStyle} />
              </EditFieldRow>

              {/* Release Name — text input (highlighted) */}
              <EditFieldRow label="Release Name" fieldId="customfield_10563" touched={touched.releaseName} highlight>
                <input type="text" value={releaseName} onChange={(e) => { setReleaseName(e.target.value); markTouched("releaseName"); }}
                  className={inputFocusRing} style={{ ...inputStyle, color: "#60a5fa", fontWeight: 600 }} />
              </EditFieldRow>

              {/* Release Type — dropdown */}
              <EditFieldRow label="Release Type" fieldId="customfield_10616" touched={touched.releaseType}>
                <select value={releaseType} onChange={(e) => { setReleaseType(e.target.value); markTouched("releaseType"); }}
                  className={inputFocusRing} style={selectStyle}>
                  {FIELD_OPTIONS.releaseType.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </EditFieldRow>
            </div>
          </div>

          {/* Description — editable textarea */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider mb-3 flex items-center gap-2" style={{ color: dk.textDim }}>
              Description
              {touched.description && <span className="text-xs font-normal rounded px-1.5 py-0.5" style={{ backgroundColor: "rgba(79,143,247,0.15)", color: dk.accent }}>modified</span>}
            </h3>
            <textarea
              value={description}
              onChange={(e) => { setDescription(e.target.value); markTouched("description"); }}
              rows={7}
              className={inputFocusRing}
              style={{
                ...inputStyle,
                resize: "vertical",
                lineHeight: 1.6,
                minHeight: 140,
              }}
            />
          </div>

          {/* Attachment */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: dk.textDim }}>Attachment</h3>
            <div className="rounded-lg p-4 flex items-center gap-3" style={{ backgroundColor: dk.surface, border: `1px solid ${dk.border}` }}>
              <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: isPurple ? "rgba(167,139,250,0.15)" : "rgba(79,143,247,0.15)" }}>
                <Paperclip size={18} style={{ color: isPurple ? dk.purple : dk.accent }} />
              </div>
              <div>
                <div className="text-sm font-medium" style={{ color: dk.text }}>
                  {isPurple ? `${patch.patch_id}.pdf` : `${patch.patch_id}.zip`}
                </div>
                <div className="text-xs" style={{ color: dk.textDim }}>
                  {isPurple ? "PDF exported from CAE-branded .docx template" : "Zipped binaries from patch folder"}
                </div>
              </div>
              <span className="ml-auto text-xs font-mono" style={{ color: dk.textDim }}>POST /rest/api/3/issue/&#123;key&#125;/attachments</span>
            </div>
          </div>

          {/* Logic callout */}
          <div className="rounded-lg p-3 flex items-start gap-3" style={{ backgroundColor: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.2)" }}>
            <AlertCircle size={16} className="mt-0.5 flex-shrink-0" style={{ color: "#fbbf24" }} />
            <div className="text-xs" style={{ color: "#fcd34d" }}>
              <strong>New/Existing logic:</strong> JQL checks{" "}
              <code className="px-1 rounded text-xs" style={{ backgroundColor: "rgba(251,191,36,0.12)" }}>project = CFSSOCP AND cf[10563] = "Version {version}"</code>.
              {isNewFolder
                ? ` No existing ticket found for version ${version} \u2014 this will create a NEW folder on the portal.`
                : ` Existing ticket found for version ${version} \u2014 this will add to the EXISTING folder on the portal.`}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 rounded-b-xl space-y-3" style={{ borderTop: `1px solid ${dk.border}`, backgroundColor: dk.surface }}>
          {/* Already on Portal toggle */}
          <div className="flex items-center justify-between">
            <button onClick={() => setAlreadyOnPortal(!alreadyOnPortal)}
              className="flex items-center gap-3 group cursor-pointer">
              <div className="w-10 h-5 rounded-full relative transition-colors"
                style={{ backgroundColor: alreadyOnPortal ? "#34d399" : dk.border }}>
                <div className="absolute top-0.5 w-4 h-4 rounded-full shadow transition-all"
                  style={{ backgroundColor: "#fff", left: alreadyOnPortal ? 22 : 2 }} />
              </div>
              <div>
                <div className="text-sm font-medium" style={{ color: alreadyOnPortal ? "#6ee7b7" : dk.textMute }}>
                  Already available on portal
                </div>
                <div className="text-xs" style={{ color: dk.textDim }}>
                  {alreadyOnPortal
                    ? "Skip Jira ticket \u2014 mark as approved & published immediately"
                    : "Turn on if this release is already live on the community portal"}
                </div>
              </div>
            </button>
            {Object.keys(touched).length > 0 && (
              <span className="text-xs px-2 py-1 rounded" style={{ backgroundColor: "rgba(251,191,36,0.12)", color: "#fbbf24" }}>
                {Object.keys(touched).length} field{Object.keys(touched).length > 1 ? "s" : ""} modified
              </span>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex items-center justify-between">
            <button onClick={onClose} className="px-4 py-2 text-sm font-medium rounded-lg transition-colors" style={{ color: dk.textMute }}>
              Cancel
            </button>
            {alreadyOnPortal ? (
              <button className="px-5 py-2.5 text-sm font-semibold text-white rounded-lg transition-colors flex items-center gap-2 shadow-sm"
                style={{ background: "linear-gradient(135deg,#059669,#047857)" }}>
                <CheckCircle2 size={16} />
                Mark as Approved & Published
              </button>
            ) : (
              <button className="px-5 py-2.5 text-sm font-semibold text-white rounded-lg transition-colors flex items-center gap-2 shadow-sm"
                style={{ background: isPurple ? "linear-gradient(135deg,#7c3aed,#6d28d9)" : "linear-gradient(135deg,#2563eb,#1d4ed8)" }}>
                <Check size={16} />
                Approve & Create Jira Ticket
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Static (locked) field row ──
const FieldRowStatic = ({ label, value, sublabel, fieldId, locked, small }) => (
  <div className="flex items-start px-4 py-3 gap-4" style={{ backgroundColor: dk.surface, borderBottom: `1px solid ${dk.border}` }}>
    <div className="w-48 flex-shrink-0 flex items-start gap-2">
      <div>
        <div className="text-sm font-medium flex items-center gap-1.5" style={{ color: dk.textMute }}>
          {label}
          {locked && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#5c5e68" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>}
        </div>
        {fieldId && <div className="text-xs font-mono" style={{ color: dk.textDim }}>{fieldId}</div>}
      </div>
    </div>
    <div className="flex-1 min-w-0">
      <div className={`${small ? "text-xs" : "text-sm"}`} style={{ color: dk.textDim }}>{value}</div>
      {sublabel && <div className="text-xs mt-0.5" style={{ color: dk.textDim }}>{sublabel}</div>}
    </div>
  </div>
);

// ── Editable field row ──
const EditFieldRow = ({ label, fieldId, touched, highlight, children }) => (
  <div className="flex items-center px-4 py-3 gap-4" style={{ backgroundColor: dk.surface, borderBottom: `1px solid ${dk.border}` }}>
    <div className="w-48 flex-shrink-0">
      <div className="text-sm font-medium flex items-center gap-1.5" style={{ color: touched ? dk.accent : dk.textMute }}>
        {label}
        {touched && <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: dk.accent }} />}
      </div>
      {fieldId && <div className="text-xs font-mono" style={{ color: dk.textDim }}>{fieldId}</div>}
    </div>
    <div className="flex-1 min-w-0">
      {children}
    </div>
  </div>
);

// ─── PATCH DETAIL MODAL (dark) ──────────────────────────────────────────────

const PatchDetailModal = ({ patch, onClose, onApprove }) => {
  if (!patch) return null;
  const product = PRODUCTS.find((p) => p.product_id === patch.product_id);

  const TimelineStep = ({ label, timestamp, isLast, active }) => (
    <div className="flex items-start gap-3">
      <div className="flex flex-col items-center">
        <div className="w-3 h-3 rounded-full border-2"
          style={{
            borderColor: active ? "#f59e0b" : timestamp ? "#34d399" : dk.borderLt,
            backgroundColor: active ? "rgba(245,158,11,0.2)" : timestamp ? "rgba(52,211,153,0.2)" : dk.surface,
          }} />
        {!isLast && <div className="w-0.5 h-6" style={{ backgroundColor: timestamp ? "rgba(52,211,153,0.3)" : dk.border }} />}
      </div>
      <div style={{ marginTop: -2 }}>
        <div className="text-sm" style={{ color: active ? "#fbbf24" : timestamp ? dk.text : dk.textDim, fontWeight: active ? 600 : 400 }}>{label}</div>
        {timestamp && timestamp !== "active" && <div className="text-xs" style={{ color: dk.textDim }}>{formatDateTime(timestamp)}</div>}
      </div>
    </div>
  );

  const binSteps = [
    { label: "Discovered", ts: patch.discovered_at },
    { label: "Downloaded", ts: patch.discovered_at },
    { label: "Pending Approval", ts: patch.binaries.status === "pending_approval" ? "active" : (patch.binaries.published_at ? patch.discovered_at : null) },
    { label: "Approved", ts: patch.binaries.approved_at },
    { label: "Published", ts: patch.binaries.published_at },
  ];
  const noteSteps = [
    { label: "Not Started", ts: patch.release_notes.status !== "not_started" ? patch.discovered_at : null },
    { label: "Discovered", ts: patch.release_notes.status !== "not_started" ? patch.discovered_at : null },
    { label: "Downloaded", ts: patch.release_notes.status !== "not_started" ? patch.discovered_at : null },
    { label: "Converted", ts: null },
    { label: "Pending Approval", ts: patch.release_notes.status === "pending_approval" ? "active" : null },
    { label: "PDF Exported", ts: null },
    { label: "Published", ts: patch.release_notes.published_at },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ backgroundColor: "rgba(0,0,0,0.7)" }}>
      <div className="w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-xl shadow-2xl" style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}>
        <div className="px-6 py-4 flex items-center justify-between" style={{ borderBottom: `1px solid ${dk.border}` }}>
          <div>
            <div className="text-xs uppercase tracking-wider" style={{ color: dk.textDim }}>{product?.display_name} / {patch.version}</div>
            <div className="text-xl font-bold" style={{ color: dk.text }}>Patch {patch.patch_id}</div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg" style={{ color: dk.textMute }}>
            <X size={20} />
          </button>
        </div>
        <div className="px-6 py-2 flex items-center gap-2 text-xs font-mono" style={{ backgroundColor: dk.surface, borderBottom: `1px solid ${dk.border}`, color: dk.textDim }}>
          <FolderOpen size={12} />
          <a href="#" onClick={(e) => e.preventDefault()} className="underline decoration-dotted underline-offset-2" style={{ color: dk.accent }}>
            {getLocalPath(patch.product_id, patch.patch_id)}/
          </a>
        </div>
        <div className="px-6 py-5 grid grid-cols-2 gap-8">
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Box size={16} style={{ color: dk.accent }} />
              <h4 className="font-semibold" style={{ color: dk.text }}>Binaries</h4>
              {patch.binaries.jira_ticket_key && (
                <a href="#" className="ml-auto text-xs flex items-center gap-1" style={{ color: dk.accent }}>
                  {patch.binaries.jira_ticket_key} <ExternalLink size={10} />
                </a>
              )}
            </div>
            {binSteps.map((s, i) => (
              <TimelineStep key={i} label={s.label} timestamp={s.ts} isLast={i === binSteps.length - 1} active={s.ts === "active"} />
            ))}
            {patch.binaries.status === "pending_approval" && (
              <button onClick={() => onApprove(patch, "binaries")}
                className="mt-4 w-full px-4 py-2 text-sm font-semibold text-white rounded-lg flex items-center justify-center gap-2"
                style={{ background: "linear-gradient(135deg,#2563eb,#1d4ed8)" }}>
                <Check size={14} /> Approve Binaries
              </button>
            )}
          </div>
          <div>
            <div className="flex items-center gap-2 mb-4">
              <FileText size={16} style={{ color: dk.purple }} />
              <h4 className="font-semibold" style={{ color: dk.text }}>Release Notes</h4>
              {patch.release_notes.jira_ticket_key && (
                <a href="#" className="ml-auto text-xs flex items-center gap-1" style={{ color: dk.purple }}>
                  {patch.release_notes.jira_ticket_key} <ExternalLink size={10} />
                </a>
              )}
            </div>
            {noteSteps.map((s, i) => (
              <TimelineStep key={i} label={s.label} timestamp={s.ts} isLast={i === noteSteps.length - 1} active={s.ts === "active"} />
            ))}
            {patch.release_notes.status === "pending_approval" && (
              <button onClick={() => onApprove(patch, "docs")}
                className="mt-4 w-full px-4 py-2 text-sm font-semibold text-white rounded-lg flex items-center justify-center gap-2"
                style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)" }}>
                <Check size={14} /> Approve Release Notes
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// ─── MAIN APP ───────────────────────────────────────────────────────────────

export default function ProductControlCenter() {
  const [currentView, setCurrentView] = useState("pipeline");
  const [statusFilter, setStatusFilter] = useState("all");
  const [productFilter, setProductFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  // Start with approval modal open on first actionable patch
  const [approvalModal, setApprovalModal] = useState({ patch: PATCHES[0], pipelineType: "binaries" });
  const [detailModal, setDetailModal] = useState(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const actionable = useMemo(() => PATCHES.filter((p) =>
    p.binaries.status !== "published" || p.release_notes.status !== "published"
  ), []);
  const history = useMemo(() => PATCHES.filter((p) =>
    p.binaries.status === "published" && p.release_notes.status === "published"
  ), []);

  const filteredActionable = useMemo(() => {
    let list = actionable;
    if (productFilter !== "all") list = list.filter((p) => p.product_id === productFilter);
    if (statusFilter !== "all") list = list.filter((p) => p.binaries.status === statusFilter || p.release_notes.status === statusFilter);
    if (searchQuery) list = list.filter((p) => p.patch_id.includes(searchQuery) || p.version.includes(searchQuery));
    return list;
  }, [actionable, productFilter, statusFilter, searchQuery]);

  const filteredHistory = useMemo(() => {
    let list = history;
    if (productFilter !== "all") list = list.filter((p) => p.product_id === productFilter);
    if (searchQuery) list = list.filter((p) => p.patch_id.includes(searchQuery) || p.version.includes(searchQuery));
    return list;
  }, [history, productFilter, searchQuery]);


  const productStats = PRODUCTS.map((prod) => {
    const patches = PATCHES.filter((p) => p.product_id === prod.product_id);
    const pendingBin = patches.filter((p) => p.binaries.status === "pending_approval").length;
    const pendingDocs = patches.filter((p) => p.release_notes.status === "pending_approval").length;
    const published = patches.filter((p) => p.binaries.status === "published" && p.release_notes.status === "published").length;
    return { ...prod, pendingBin, pendingDocs, published, patches: patches.length };
  });

  return (
    <div className="flex h-screen" style={{ backgroundColor: dk.bg, color: dk.text, fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>
      {/* ─── SIDEBAR ───────────────────────────────────── */}
      <aside className={`${sidebarCollapsed ? "w-16" : "w-64"} flex flex-col transition-all duration-200`}
        style={{ backgroundColor: "#0b0d12", borderRight: `1px solid ${dk.border}` }}>
        <div className="px-4 flex items-center gap-3" style={{ borderBottom: `1px solid ${dk.border}`, height: 65 }}>
          <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{ background: "linear-gradient(135deg,#2563eb,#1d4ed8)" }}>
            <Activity size={18} className="text-white" />
          </div>
          {!sidebarCollapsed && (
            <span className="text-sm font-bold" style={{ color: dk.text }}>OpsComm Control Center</span>
          )}
        </div>

        {!sidebarCollapsed && (
          <div className="px-3 pt-4 pb-2">
            <div className="text-xs font-semibold uppercase tracking-wider px-2 mb-2" style={{ color: dk.textDim }}>Modules</div>
          </div>
        )}
        <nav className="flex-1 px-2 space-y-1">
          <button onClick={() => setCurrentView("dashboard")}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors`}
            style={{
              backgroundColor: currentView === "dashboard" ? dk.accent : "transparent",
              color: currentView === "dashboard" ? "#fff" : dk.textMute,
            }}>
            <LayoutDashboard size={18} />
            {!sidebarCollapsed && "Dashboard"}
          </button>
          <button onClick={() => setCurrentView("pipeline")}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors"
            style={{
              backgroundColor: currentView === "pipeline" ? dk.accent : "transparent",
              color: currentView === "pipeline" ? "#fff" : dk.textMute,
            }}>
            <FileText size={18} />
            {!sidebarCollapsed && "Documentation Pipeline"}
          </button>
          {!sidebarCollapsed && (
            <>
              <div className="pt-4 pb-2">
                <div className="text-xs font-semibold uppercase tracking-wider px-2 mb-2" style={{ color: dk.textDim }}>Future Modules</div>
              </div>
              <div className="px-3 py-2 text-xs flex items-center gap-2" style={{ color: dk.textDim }}>
                <Zap size={14} /> Email Triage Pipeline
              </div>
              <div className="px-3 py-2 text-xs flex items-center gap-2" style={{ color: dk.textDim }}>
                <Zap size={14} /> PM Integration
              </div>
            </>
          )}
        </nav>
        <div className="px-2 py-3" style={{ borderTop: `1px solid ${dk.border}` }}>
          <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors"
            style={{ color: dk.textDim }}>
            {sidebarCollapsed ? <ChevronRight size={16} /> : <><ChevronDown size={16} /> Collapse</>}
          </button>
        </div>
      </aside>

      {/* ─── MAIN CONTENT ──────────────────────────────── */}
      <main className="flex-1 overflow-y-auto">
        {/* Top bar */}
        <header className="px-6 flex items-center justify-between sticky top-0 z-10"
          style={{ backgroundColor: dk.surface, borderBottom: `1px solid ${dk.border}`, height: 65 }}>
          <div>
            <h1 className="text-xl font-bold" style={{ color: dk.text }}>
              {currentView === "dashboard" ? "Dashboard" : "Documentation Pipeline"}
            </h1>
            <p className="text-sm" style={{ color: dk.textDim }}>OpsComm Docs & Binaries Pipeline</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs" style={{ color: dk.textDim }}>Last scan: Apr 3, 2026 17:04</span>
            <button className="flex items-center gap-2 px-4 py-2 text-white text-sm font-medium rounded-lg shadow-sm"
              style={{ background: "linear-gradient(135deg,#2563eb,#1d4ed8)" }}>
              <RefreshCw size={14} /> Scan SFTP
            </button>
          </div>
        </header>

        <div className="p-6">
          {/* ─── DASHBOARD VIEW ─────────────────── */}
          {currentView === "dashboard" && (
            <div className="space-y-6">
              {/* Review needed + Products overview */}
              <div className="grid grid-cols-3 gap-4">
                {/* Patches need review */}
                <div className="rounded-xl p-5 flex items-center gap-4" style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}>
                  <div className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ backgroundColor: actionable.length > 0 ? "rgba(251,191,36,0.15)" : "rgba(52,211,153,0.15)" }}>
                    <AlertCircle size={22} style={{ color: actionable.length > 0 ? "#fbbf24" : "#34d399" }} />
                  </div>
                  <div>
                    <div className="text-3xl font-bold" style={{ color: actionable.length > 0 ? "#fbbf24" : "#34d399" }}>{actionable.length}</div>
                    <div className="text-sm" style={{ color: dk.textMute }}>
                      {actionable.length === 1 ? "patch needs" : "patches need"} review
                    </div>
                  </div>
                </div>

                {/* Products — single card with all 3 */}
                <div className="col-span-2 rounded-xl p-5" style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold" style={{ color: dk.textMute }}>Tracked Products</h3>
                    <span className="text-xs" style={{ color: dk.textDim }}>Latest official version</span>
                  </div>
                  <div className="space-y-3">
                    {productStats.map((prod) => {
                      // Find latest published version for this product
                      const publishedPatches = PATCHES.filter(
                        (p) => p.product_id === prod.product_id && p.binaries.status === "published"
                      );
                      const latestVersion = publishedPatches.length > 0
                        ? publishedPatches.sort((a, b) => b.version.localeCompare(a.version, undefined, { numeric: true }))[0].version
                        : "—";
                      return (
                        <div key={prod.product_id}
                          className="flex items-center justify-between py-2 px-3 rounded-lg cursor-pointer transition-colors"
                          style={{ backgroundColor: dk.surface }}
                          onClick={() => { setProductFilter(prod.product_id); setCurrentView("pipeline"); }}>
                          <div className="flex items-center gap-3">
                            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: prod.pendingBin > 0 ? "#f59e0b" : "#34d399" }} />
                            <span className="font-medium text-sm" style={{ color: dk.text }}>{prod.display_name}</span>
                          </div>
                          <div className="flex items-center gap-4">
                            {prod.pendingBin > 0 && (
                              <span className="text-xs px-2 py-0.5 rounded-full" style={{ backgroundColor: "rgba(251,191,36,0.15)", color: "#fbbf24" }}>
                                {prod.pendingBin + prod.pendingDocs} pending
                              </span>
                            )}
                            <span className="font-mono text-sm font-semibold" style={{ color: dk.accent }}>v{latestVersion}</span>
                            <ChevronRight size={14} style={{ color: dk.textDim }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Quick actionable */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-lg font-semibold" style={{ color: dk.text }}>Actionable Patches</h2>
                  <button onClick={() => setCurrentView("pipeline")} className="text-sm flex items-center gap-1" style={{ color: dk.accent }}>
                    View all <ArrowRight size={14} />
                  </button>
                </div>
                <div className="rounded-xl overflow-hidden" style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm" style={{ minWidth: 700 }}>
                      <thead>
                        <tr style={{ borderBottom: `1px solid ${dk.border}` }}>
                          <Th>Product</Th><Th>Patch</Th><Th>Binaries</Th><Th>Release Notes</Th><Th align="right">Actions</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {actionable.slice(0, 5).map((p) => (
                          <tr key={p.patch_id} style={{ borderBottom: `1px solid ${dk.border}` }}>
                            <Td muted>{PRODUCTS.find(pr => pr.product_id === p.product_id)?.display_name}</Td>
                            <Td mono bold>{p.patch_id}</Td>
                            <Td><StatusBadge status={p.binaries.status} /></Td>
                            <Td><StatusBadge status={p.release_notes.status} /></Td>
                            <Td align="right" nowrap>
                              <button onClick={() => setDetailModal(p)} className="p-1 rounded mr-1 inline-flex" style={{ color: dk.textDim }}><Eye size={14} /></button>
                              {p.binaries.status === "pending_approval" && (
                                <button onClick={() => setApprovalModal({ patch: p, pipelineType: "binaries" })}
                                  className="text-xs font-medium px-3 py-1.5 rounded-md text-white mr-1"
                                  style={{ background: "linear-gradient(135deg,#2563eb,#1d4ed8)" }}>Approve Bin</button>
                              )}
                              {p.release_notes.status === "pending_approval" && (
                                <button onClick={() => setApprovalModal({ patch: p, pipelineType: "docs" })}
                                  className="text-xs font-medium px-3 py-1.5 rounded-md text-white"
                                  style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)" }}>Approve Docs</button>
                              )}
                            </Td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ─── PIPELINE VIEW ──────────────────── */}
          {currentView === "pipeline" && (
            <div className="space-y-5">
              {/* Filters */}
              <div className="rounded-xl p-4 flex items-center gap-4 flex-wrap"
                style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}>
                <div className="relative flex-1 max-w-xs">
                  <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: dk.textDim }} />
                  <input type="text" placeholder="Search patches..." value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-9 pr-4 py-2 text-sm rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                    style={{ backgroundColor: dk.surface, border: `1px solid ${dk.border}`, color: dk.text }} />
                </div>
                <div className="flex items-center gap-2">
                  <Filter size={14} style={{ color: dk.textDim }} />
                  <select value={productFilter} onChange={(e) => setProductFilter(e.target.value)}
                    className="text-sm rounded-lg px-3 py-2 focus:outline-none"
                    style={{ backgroundColor: dk.surface, border: `1px solid ${dk.border}`, color: dk.text }}>
                    <option value="all">All Products</option>
                    {PRODUCTS.map((p) => <option key={p.product_id} value={p.product_id}>{p.display_name}</option>)}
                  </select>
                  <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                    className="text-sm rounded-lg px-3 py-2 focus:outline-none"
                    style={{ backgroundColor: dk.surface, border: `1px solid ${dk.border}`, color: dk.text }}>
                    <option value="all">All Statuses</option>
                    <option value="pending_approval">Pending Approval</option>
                    <option value="not_started">Not Started</option>
                    <option value="published">Published</option>
                  </select>
                </div>
                <div className="ml-auto text-xs" style={{ color: dk.textDim }}>
                  {filteredActionable.length} actionable, {filteredHistory.length} published
                </div>
              </div>

              {/* Actionable */}
              <div>
                <h2 className="text-base font-semibold mb-3 flex items-center gap-2" style={{ color: dk.text }}>
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: "#f59e0b" }} />
                  Actionable ({filteredActionable.length})
                </h2>
                <div className="rounded-xl overflow-hidden" style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm" style={{ minWidth: 900 }}>
                      <thead>
                        <tr style={{ borderBottom: `1px solid ${dk.border}` }}>
                          <Th>Product</Th><Th>Patch ID</Th><Th>Local Path</Th><Th>Binaries</Th><Th>Release Notes</Th><Th align="right">Actions</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredActionable.map((p) => (
                          <tr key={`${p.product_id}-${p.patch_id}`} style={{ borderBottom: `1px solid ${dk.border}` }}>
                            <Td muted small>{PRODUCTS.find(pr => pr.product_id === p.product_id)?.display_name}</Td>
                            <Td mono bold>{p.patch_id}</Td>
                            <Td mono small>
                              <a href="#" onClick={(e) => e.preventDefault()}
                                className="underline decoration-dotted underline-offset-2"
                                style={{ color: dk.accent }}
                                title={`Open ${getLocalPath(p.product_id, p.patch_id)}`}>
                                {getLocalPath(p.product_id, p.patch_id)}/
                              </a>
                            </Td>
                            <Td><StatusBadge status={p.binaries.status} /></Td>
                            <Td><StatusBadge status={p.release_notes.status} /></Td>
                            <Td align="right" nowrap>
                              <button onClick={() => setDetailModal(p)} className="p-1 rounded mr-1 inline-flex" style={{ color: dk.textDim }}>
                                <Eye size={14} />
                              </button>
                              {p.binaries.status === "pending_approval" && (
                                <button onClick={() => setApprovalModal({ patch: p, pipelineType: "binaries" })}
                                  className="text-xs font-medium px-3 py-1.5 rounded-md text-white mr-1"
                                  style={{ background: "linear-gradient(135deg,#2563eb,#1d4ed8)" }}>
                                  Approve Bin
                                </button>
                              )}
                              {p.release_notes.status === "pending_approval" && (
                                <button onClick={() => setApprovalModal({ patch: p, pipelineType: "docs" })}
                                  className="text-xs font-medium px-3 py-1.5 rounded-md text-white"
                                  style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)" }}>
                                  Approve Docs
                                </button>
                              )}
                            </Td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              {/* History */}
              <div>
                <button onClick={() => setShowHistory(!showHistory)}
                  className="flex items-center gap-2 text-base font-semibold mb-3 transition-colors" style={{ color: dk.text }}>
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
                            <Th>Product</Th><Th>Patch ID</Th><Th>Binaries</Th><Th>Jira (Bin)</Th><Th>Release Notes</Th><Th>Jira (Docs)</Th><Th>Published</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredHistory.map((p) => (
                            <tr key={`${p.product_id}-${p.patch_id}`}
                              className="cursor-pointer" onClick={() => setDetailModal(p)}
                              style={{ borderBottom: `1px solid ${dk.border}` }}>
                              <Td muted small>{PRODUCTS.find(pr => pr.product_id === p.product_id)?.display_name}</Td>
                              <Td mono bold>{p.patch_id}</Td>
                              <Td><StatusBadge status="published" /></Td>
                              <Td>
                                <a href="#" className="text-xs flex items-center gap-1" style={{ color: dk.accent }}
                                  onClick={(e) => e.stopPropagation()}>
                                  {p.binaries.jira_ticket_key} <ExternalLink size={10} />
                                </a>
                              </Td>
                              <Td><StatusBadge status="published" /></Td>
                              <Td>
                                <a href="#" className="text-xs flex items-center gap-1" style={{ color: dk.purple }}
                                  onClick={(e) => e.stopPropagation()}>
                                  {p.release_notes.jira_ticket_key} <ExternalLink size={10} />
                                </a>
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
            </div>
          )}
        </div>
      </main>

      {/* ─── MODALS ────────────────────────────────────── */}
      {approvalModal && (
        <JiraApprovalModal patch={approvalModal.patch} pipelineType={approvalModal.pipelineType} onClose={() => setApprovalModal(null)} />
      )}
      {detailModal && (
        <PatchDetailModal patch={detailModal} onClose={() => setDetailModal(null)}
          onApprove={(patch, type) => { setDetailModal(null); setApprovalModal({ patch, pipelineType: type }); }} />
      )}
    </div>
  );
}

// ─── TABLE PRIMITIVES ───────────────────────────────────────────────────────

const Th = ({ children, align }) => (
  <th className={`px-4 py-3 text-xs font-semibold uppercase tracking-wider ${align === "right" ? "text-right" : "text-left"}`}
    style={{ backgroundColor: dk.surface, color: dk.textDim }}>
    {children}
  </th>
);

const Td = ({ children, mono, bold, muted, small, align, nowrap, truncate }) => (
  <td className={`px-4 py-3 ${mono ? "font-mono" : ""} ${truncate ? "max-w-xs truncate" : ""} ${nowrap ? "whitespace-nowrap" : ""} ${align === "right" ? "text-right" : ""}`}
    style={{ color: muted ? dk.textDim : dk.text, fontSize: small ? 12 : 14, fontWeight: bold ? 600 : 400 }}>
    {children}
  </td>
);


