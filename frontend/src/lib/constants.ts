// Dark theme tokens
export const dk = {
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

// Status display config
export const STATUS_CONFIG: Record<string, { label: string; bg: string; text: string; dot: string }> = {
  not_started:       { label: "Not Started",       bg: "rgba(107,114,128,0.15)", text: "#9ca3af", dot: "#6b7280" },
  discovered:        { label: "Discovered",        bg: "rgba(96,165,250,0.15)",  text: "#93c5fd", dot: "#60a5fa" },
  downloaded:        { label: "Downloaded",        bg: "rgba(129,140,248,0.15)", text: "#a5b4fc", dot: "#818cf8" },
  pending_approval:  { label: "Pending Approval",  bg: "rgba(251,191,36,0.15)",  text: "#fbbf24", dot: "#f59e0b" },
  approved:          { label: "Approved",          bg: "rgba(34,211,238,0.15)",  text: "#67e8f9", dot: "#22d3ee" },
  converted:         { label: "Converted",         bg: "rgba(192,132,252,0.15)", text: "#c4b5fd", dot: "#a78bfa" },
  pdf_exported:      { label: "PDF Exported",      bg: "rgba(45,212,191,0.15)",  text: "#5eead4", dot: "#2dd4bf" },
  published:         { label: "Published",         bg: "rgba(52,211,153,0.12)",  text: "#6ee7b7", dot: "#34d399" },
  not_found:         { label: "Not Found",         bg: "rgba(239,68,68,0.12)",   text: "#fca5a5", dot: "#ef4444" },
};

// Jira field options (from pipeline.json)
export const FIELD_OPTIONS = {
  client: ["Flightscape", "CAE", "Other"],
  environment: ["All the three", "Production", "Staging", "Development"],
  releaseType: ["Version", "Update", "Patch", "Sub Component"],
  createUpdateRemove: ["New CAE Portal Release", "Existing CAE Portal Release", "Remove CAE Portal Release"],
};

// Shared input styles (inline style objects for Jira modal)
export const inputStyle: React.CSSProperties = {
  backgroundColor: "rgba(255,255,255,0.04)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 6,
  color: "#e4e5e9",
  fontSize: 14,
  padding: "6px 10px",
  width: "100%",
  outline: "none",
};

export const selectStyle: React.CSSProperties = {
  ...inputStyle,
  appearance: "none" as const,
  backgroundImage: `url("data:image/svg+xml,%3Csvg width='12' height='8' viewBox='0 0 12 8' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1.5L6 6.5L11 1.5' stroke='%238b8d97' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")`,
  backgroundRepeat: "no-repeat",
  backgroundPosition: "right 10px center",
  paddingRight: 32,
  cursor: "pointer",
};

// Date formatting helpers
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
