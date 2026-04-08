import { Outlet, useLocation } from "react-router-dom";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import Sidebar from "./Sidebar";
import Header from "./Header";
import { getDashboardSummary } from "../../lib/api";
import { scanSftp } from "../../lib/api";
import { dk } from "../../lib/constants";
import type { ApiError } from "../../lib/api";

export default function AppLayout() {
  const location = useLocation();
  const queryClient = useQueryClient();

  const { data: lastScan } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: getDashboardSummary,
    select: (d) => d.last_scan,
  });

  const scanMutation = useMutation({
    mutationFn: () => scanSftp(),
    onSuccess: (data) => {
      if (data.total_new > 0) {
        toast.success(`Scan complete — ${data.total_new} new patch${data.total_new > 1 ? "es" : ""} found`);
      } else {
        toast.info("No new patches found");
      }
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      queryClient.invalidateQueries({ queryKey: ["patches"] });
    },
    onError: (err: ApiError) => {
      toast.error(`Scan failed: ${err.detail || err.message}`);
    },
  });

  const title = location.pathname === "/pipeline" ? "Documentation Pipeline" : "Dashboard";

  return (
    <div
      className="flex h-screen"
      style={{ backgroundColor: dk.bg, color: dk.text, fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}
    >
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Header
          title={title}
          subtitle="OpsComm Docs & Binaries Pipeline"
          lastScan={lastScan ?? null}
          onScan={() => scanMutation.mutate()}
          isScanning={scanMutation.isPending}
        />
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
