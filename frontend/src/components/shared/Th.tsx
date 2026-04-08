import type { ReactNode } from "react";
import { dk } from "../../lib/constants";

interface ThProps {
  children: ReactNode;
  align?: "left" | "right";
}

export default function Th({ children, align = "left" }: ThProps) {
  return (
    <th
      className={`px-4 py-3 text-xs font-semibold uppercase tracking-wider ${align === "right" ? "text-right" : "text-left"}`}
      style={{ backgroundColor: dk.surface, color: dk.textDim }}
    >
      {children}
    </th>
  );
}
