import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ChevronRight, ArrowRight, Eye, Check } from "lucide-react";
import { getDashboardSummary, getPatches } from "../lib/api";
import { dk } from "../lib/constants";
import StatusBadge from "../components/shared/StatusBadge";
import SummaryCard from "../components/shared/SummaryCard";
import Th from "../components/shared/Th";
import Td from "../components/shared/Td";

export default function Dashboard() {
  const navigate = useNavigate();

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: getDashboardSummary,
  });

  const { data: patchList, isLoading: patchesLoading } = useQuery({
    queryKey: ["patches"],
    queryFn: () => getPatches(),
  });

  const isLoading = summaryLoading || patchesLoading;

  // Build product name lookup from summary
  const productNames = new Map(
    summary?.by_product.map((p) => [p.product_id, p.display_name]) ?? [],
  );

  // Derive latest published version per product from patch history
  const latestVersions = new Map<string, string>();
  if (patchList) {
    for (const p of patchList.history) {
      const current = latestVersions.get(p.product_id);
      if (!current || p.version.localeCompare(current, undefined, { numeric: true }) > 0) {
        latestVersions.set(p.product_id, p.version);
      }
    }
  }

  const actionableCount = patchList?.actionable.length ?? 0;

  // Loading skeleton
  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-3 gap-4">
          <div className="rounded-xl p-5 h-28 animate-pulse" style={{ backgroundColor: dk.card }} />
          <div className="col-span-2 rounded-xl p-5 h-28 animate-pulse" style={{ backgroundColor: dk.card }} />
        </div>
        <div className="rounded-xl p-5 animate-pulse" style={{ backgroundColor: dk.card, height: 300 }} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top row: review count + tracked products */}
      <div className="grid grid-cols-3 gap-4">
        {/* Patches need review */}
        <SummaryCard
          icon={<AlertCircle size={22} style={{ color: actionableCount > 0 ? "#fbbf24" : "#34d399" }} />}
          iconBg={actionableCount > 0 ? "rgba(251,191,36,0.15)" : "rgba(52,211,153,0.15)"}
          value={actionableCount}
          valueColor={actionableCount > 0 ? "#fbbf24" : "#34d399"}
          label={actionableCount === 1 ? "patch needs review" : "patches need review"}
        />

        {/* Tracked products */}
        <div className="col-span-2 rounded-xl p-5" style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold" style={{ color: dk.textMute }}>Tracked Products</h3>
            <span className="text-xs" style={{ color: dk.textDim }}>Latest official version</span>
          </div>
          <div className="space-y-3">
            {summary?.by_product.map((prod) => (
              <div
                key={prod.product_id}
                className="flex items-center justify-between py-2 px-3 rounded-lg cursor-pointer transition-colors hover:brightness-110"
                style={{ backgroundColor: dk.surface }}
                onClick={() => navigate(`/pipeline?product=${prod.product_id}`)}
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: prod.actionable > 0 ? "#f59e0b" : "#34d399" }}
                  />
                  <span className="font-medium text-sm" style={{ color: dk.text }}>{prod.display_name}</span>
                </div>
                <div className="flex items-center gap-4">
                  {prod.actionable > 0 && (
                    <span
                      className="text-xs px-2 py-0.5 rounded-full"
                      style={{ backgroundColor: "rgba(251,191,36,0.15)", color: "#fbbf24" }}
                    >
                      {prod.actionable} pending
                    </span>
                  )}
                  <span className="font-mono text-sm font-semibold" style={{ color: dk.accent }}>
                    v{latestVersions.get(prod.product_id) || "\u2014"}
                  </span>
                  <ChevronRight size={14} style={{ color: dk.textDim }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Actionable patches table */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold" style={{ color: dk.text }}>Actionable Patches</h2>
          <button
            onClick={() => navigate("/pipeline")}
            className="text-sm flex items-center gap-1"
            style={{ color: dk.accent }}
          >
            View all <ArrowRight size={14} />
          </button>
        </div>

        {actionableCount === 0 ? (
          <div
            className="rounded-xl p-10 text-center"
            style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}
          >
            <p className="text-sm" style={{ color: dk.textMute }}>
              All patches are published. Run a scan to check for new ones.
            </p>
          </div>
        ) : (
          <div className="rounded-xl overflow-hidden" style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm" style={{ minWidth: 700 }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${dk.border}` }}>
                    <Th>Product</Th>
                    <Th>Patch</Th>
                    <Th>Binaries</Th>
                    <Th>Release Notes</Th>
                    <Th align="right">Actions</Th>
                  </tr>
                </thead>
                <tbody>
                  {patchList?.actionable.slice(0, 5).map((p) => (
                    <tr key={`${p.product_id}-${p.patch_id}`} style={{ borderBottom: `1px solid ${dk.border}` }}>
                      <Td muted>{productNames.get(p.product_id) ?? p.product_id}</Td>
                      <Td mono bold>{p.patch_id}</Td>
                      <Td><StatusBadge status={p.binaries.status} /></Td>
                      <Td><StatusBadge status={p.release_notes.status} /></Td>
                      <Td align="right" nowrap>
                        <button className="p-1 rounded mr-1 inline-flex" style={{ color: dk.textDim }}>
                          <Eye size={14} />
                        </button>
                        {p.binaries.status === "pending_approval" && (
                          <button
                            className="px-2.5 py-1 text-xs font-semibold text-white rounded-md inline-flex items-center gap-1"
                            style={{ background: "linear-gradient(135deg,#2563eb,#1d4ed8)" }}
                          >
                            <Check size={12} /> Bin
                          </button>
                        )}
                        {p.release_notes.status === "pending_approval" && (
                          <button
                            className="px-2.5 py-1 text-xs font-semibold text-white rounded-md inline-flex items-center gap-1 ml-1"
                            style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)" }}
                          >
                            <Check size={12} /> Docs
                          </button>
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
    </div>
  );
}
