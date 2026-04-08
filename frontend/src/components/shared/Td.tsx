import type { ReactNode } from "react";
import { dk } from "../../lib/constants";

interface TdProps {
  children: ReactNode;
  mono?: boolean;
  bold?: boolean;
  muted?: boolean;
  align?: "left" | "right";
  nowrap?: boolean;
}

export default function Td({ children, mono, bold, muted, align, nowrap }: TdProps) {
  return (
    <td
      className={[
        "px-4 py-3 text-sm",
        mono && "font-mono",
        nowrap && "whitespace-nowrap",
        align === "right" ? "text-right" : "text-left",
      ].filter(Boolean).join(" ")}
      style={{
        color: muted ? dk.textMute : dk.text,
        fontWeight: bold ? 600 : 400,
      }}
    >
      {children}
    </td>
  );
}
