import { useState } from "react";
import { NavLink } from "react-router-dom";
import { Activity, LayoutDashboard, FileText, Zap, ChevronRight, ChevronDown } from "lucide-react";
import { dk } from "../../lib/constants";

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  const fadeStyle = {
    opacity: collapsed ? 0 : 1,
    transition: "opacity 200ms",
  } as const;

  // Always use the expanded link class — sidebar overflow-hidden clips text when narrow
  const linkClass = "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors";

  return (
    <aside
      className={`${collapsed ? "w-16" : "w-64"} flex flex-col overflow-hidden transition-all duration-200`}
      style={{ backgroundColor: "#0b0d12", borderRight: `1px solid ${dk.border}` }}
    >
      {/* Logo */}
      <div className="px-4 flex items-center gap-3" style={{ borderBottom: `1px solid ${dk.border}`, height: 65 }}>
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ background: "linear-gradient(135deg,#2563eb,#1d4ed8)" }}
        >
          <Activity size={18} className="text-white" />
        </div>
        <span
          className="text-sm font-bold whitespace-nowrap"
          style={{ ...fadeStyle, color: dk.text }}
        >
          OpsComm Control Center
        </span>
      </div>

      {/* Section label */}
      <div
        className="px-3 overflow-hidden transition-all duration-200"
        style={{ maxHeight: collapsed ? 0 : 40, opacity: collapsed ? 0 : 1 }}
      >
        <div className="pt-4 pb-2">
          <div className="text-xs font-semibold uppercase tracking-wider px-2 mb-2 whitespace-nowrap" style={{ color: dk.textDim }}>Modules</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-2">
        <NavLink
          to="/"
          end
          className={linkClass}
          style={({ isActive }) => ({
            backgroundColor: isActive ? dk.accent : "transparent",
            color: isActive ? "#fff" : dk.textMute,
          })}
        >
          <LayoutDashboard size={18} className="flex-shrink-0" />
          <span className="whitespace-nowrap" style={fadeStyle}>Dashboard</span>
        </NavLink>
        <NavLink
          to="/pipeline"
          className={linkClass}
          style={({ isActive }) => ({
            backgroundColor: isActive ? dk.accent : "transparent",
            color: isActive ? "#fff" : dk.textMute,
          })}
        >
          <FileText size={18} className="flex-shrink-0" />
          <span className="whitespace-nowrap" style={fadeStyle}>Documentation Pipeline</span>
        </NavLink>

        {/* Future modules */}
        <div
          className="overflow-hidden transition-all duration-200"
          style={{ maxHeight: collapsed ? 0 : 200, opacity: collapsed ? 0 : 1 }}
        >
          <div className="pt-4 pb-2">
            <div className="text-xs font-semibold uppercase tracking-wider px-2 mb-2 whitespace-nowrap" style={{ color: dk.textDim }}>Future Modules</div>
          </div>
          <div className="px-3 py-2 text-xs flex items-center gap-2 whitespace-nowrap" style={{ color: dk.textDim }}>
            <Zap size={14} /> Email Triage Pipeline
          </div>
          <div className="px-3 py-2 text-xs flex items-center gap-2 whitespace-nowrap" style={{ color: dk.textDim }}>
            <Zap size={14} /> PM Integration
          </div>
        </div>
      </nav>

      {/* Collapse toggle */}
      <div className="px-2 py-3" style={{ borderTop: `1px solid ${dk.border}` }}>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors whitespace-nowrap"
          style={{ color: dk.textDim }}
        >
          {collapsed ? <ChevronRight size={16} /> : <><ChevronDown size={16} /> <span style={fadeStyle}>Collapse</span></>}
        </button>
      </div>
    </aside>
  );
}
