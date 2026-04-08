import type { ReactNode } from "react";
import { dk } from "../../lib/constants";

interface SummaryCardProps {
  icon: ReactNode;
  value: number;
  label: string;
  valueColor?: string;
  iconBg?: string;
}

export default function SummaryCard({ icon, value, label, valueColor, iconBg }: SummaryCardProps) {
  return (
    <div
      className="rounded-xl p-5 flex items-center gap-4"
      style={{ backgroundColor: dk.card, border: `1px solid ${dk.border}` }}
    >
      <div
        className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0"
        style={{ backgroundColor: iconBg || "rgba(79,143,247,0.15)" }}
      >
        {icon}
      </div>
      <div>
        <div className="text-3xl font-bold" style={{ color: valueColor || dk.text }}>{value}</div>
        <div className="text-sm" style={{ color: dk.textMute }}>{label}</div>
      </div>
    </div>
  );
}
