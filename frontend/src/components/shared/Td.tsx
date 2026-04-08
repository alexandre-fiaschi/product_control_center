import type { ReactNode } from "react";
import { dk } from "../../lib/constants";

interface TdProps {
  children: ReactNode;
  mono?: boolean;
  bold?: boolean;
  muted?: boolean;
  small?: boolean;
  align?: "left" | "right";
  nowrap?: boolean;
}

export default function Td({ children, mono, bold, muted, small, align, nowrap }: TdProps) {
  return (
    <td
      className={[
        small ? "px-4 py-3 text-xs" : "px-4 py-3 text-sm",
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
