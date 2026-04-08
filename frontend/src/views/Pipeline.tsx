import { useState, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search, Filter, ChevronUp, ChevronDown, Eye, ExternalLink } from "lucide-react";
import { getPatches, getProducts } from "../lib/api";
import { dk, formatDate } from "../lib/constants";
import StatusBadge from "../components/shared/StatusBadge";
import Th from "../components/shared/Th";
import Td from "../components/shared/Td";

function getLocalPath(productId: string, patchId: string): string {
  return `patches/${productId}/${patchId}`;
}

export default function Pipeline() {
  const [searchParams] = useSearchParams();
  const [productFilter, setProductFilter] = useState(searchParams.get("product") || "all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [showHistory, setShowHistory] = useState(false);

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
    if (statusFilter !== "all") list = list.filter((p) => p.binaries.status === statusFilter || p.release_notes.status === statusFilter);
    if (searchQuery) list = list.filter((p) => p.patch_id.includes(searchQuery) || p.version.includes(searchQuery));
    return list;
  }, [patchList?.actionable, productFilter, statusFilter, searchQuery]);

  const filteredHistory = useMemo(() => {
    let list = patchList?.history ?? [];
    if (productFilter !== "all") list = list.filter((p) => p.product_id === productFilter);
    if (searchQuery) list = list.filter((p) => p.patch_id.includes(searchQuery) || p.version.includes(searchQuery));
    return list;
  }, [patchList?.history, productFilter, searchQuery]);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="rounded-xl p-4 h-14 animate-pulse" style={{ backgroundColor: dk.card }} />
        <div className="rounded-xl p-5 animate-pulse" style={{ backgroundColor: dk.card, height: 300 }} />
        <div className="rounded-xl p-5 animate-pulse" style={{ backgroundColor: dk.card, height: 120 }} />
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
            <option value="published">Published</option>
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
                      <Td><StatusBadge status={p.binaries.status} /></Td>
                      <Td><StatusBadge status={p.release_notes.status} /></Td>
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
                        <button className="p-1 rounded mr-1 inline-flex" style={{ color: dk.textDim }}>
                          <Eye size={14} />
                        </button>
                        {p.binaries.status !== "published" && (
                          <button
                            disabled={p.binaries.status !== "pending_approval"}
                            className="px-2.5 py-1 text-xs font-semibold rounded-md inline-flex items-center gap-1"
                            style={p.binaries.status === "pending_approval"
                              ? { background: "linear-gradient(135deg,#2563eb,#1d4ed8)", color: "#fff" }
                              : { backgroundColor: dk.surface, border: `1px solid ${dk.border}`, color: dk.textDim, opacity: 0.6, cursor: "not-allowed" }}
                          >
                            Approve Bin
                          </button>
                        )}
                        {p.release_notes.status !== "published" && (
                          <button
                            disabled={p.release_notes.status !== "pending_approval"}
                            className="px-2.5 py-1 text-xs font-semibold rounded-md inline-flex items-center gap-1 ml-1"
                            style={p.release_notes.status === "pending_approval"
                              ? { background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }
                              : { backgroundColor: dk.surface, border: `1px solid ${dk.border}`, color: dk.textDim, opacity: 0.6, cursor: "not-allowed" }}
                          >
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
    </div>
  );
}
