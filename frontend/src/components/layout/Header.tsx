import { RefreshCw } from "lucide-react";
import { dk, formatDateTime } from "../../lib/constants";

interface HeaderProps {
  title: string;
  subtitle?: string;
  lastScan: string | null;
  onScan: () => void;
  isScanning: boolean;
}

export default function Header({ title, subtitle, lastScan, onScan, isScanning }: HeaderProps) {
  return (
    <header
      className="px-6 flex items-center justify-between sticky top-0 z-10"
      style={{ backgroundColor: dk.surface, borderBottom: `1px solid ${dk.border}`, height: 65 }}
    >
      <div>
        <h1 className="text-xl font-bold" style={{ color: dk.text }}>{title}</h1>
        {subtitle && <p className="text-sm" style={{ color: dk.textDim }}>{subtitle}</p>}
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xs" style={{ color: dk.textDim }}>Last scan: {formatDateTime(lastScan)}</span>
        <button
          onClick={onScan}
          disabled={isScanning}
          className="flex items-center gap-2 px-4 py-2 text-white text-sm font-medium rounded-lg shadow-sm disabled:opacity-60"
          style={{ background: "linear-gradient(135deg,#2563eb,#1d4ed8)" }}
        >
          <RefreshCw size={14} className={isScanning ? "animate-spin" : ""} />
          {isScanning ? "Scanning..." : "Scan SFTP"}
        </button>
      </div>
    </header>
  );
}
