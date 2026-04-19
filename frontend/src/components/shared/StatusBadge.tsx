import { Loader2 } from "lucide-react";
import { STATUS_CONFIG } from "../../lib/constants";
import type { LastRun } from "../../lib/types";

interface Props {
  status: string;
  lastRun?: LastRun;
  onRetry?: () => void;
}

export default function StatusBadge({ status, lastRun, onRetry }: Props) {
  const c = STATUS_CONFIG[status] || STATUS_CONFIG.not_started;
  const running = lastRun?.state === "running";
  const failed = lastRun?.state === "failed";

  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
        style={{ backgroundColor: c.bg, color: c.text }}
      >
        <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: c.dot }} />
        {c.label}
      </span>
      {running && (
        <Loader2
          size={12}
          className="animate-spin"
          style={{ color: "#60a5fa" }}
          aria-label="Running"
          // title on svg is flaky across browsers; wrap in span if tooltip misbehaves.
          // For now the status cell already shows activity via the adjacent spinner.
          // Include step in aria-label for screen readers.
        />
      )}
      {failed && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onRetry?.(); }}
          className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full hover:ring-2 hover:ring-red-400/40 transition"
          style={{ backgroundColor: "#ef4444" }}
          title={
            `Failed${lastRun?.step ? ` at ${lastRun.step}` : ""}` +
            (lastRun?.error ? `\n${lastRun.error}` : "") +
            (lastRun?.finished_at ? `\n${new Date(lastRun.finished_at).toLocaleString()}` : "") +
            (onRetry ? "\n\nClick to retry" : "")
          }
          aria-label="Last run failed — click to retry"
        />
      )}
    </span>
  );
}
