import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  TrendingUp,
  History,
  Search,
  Brain,
  Settings,
  Activity,
} from "lucide-react";
import clsx from "clsx";
import { useOkaneStore } from "../../store";

const NAV = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/positions", icon: TrendingUp, label: "Positions" },
  { to: "/history", icon: History, label: "Trade History" },
  { to: "/scanner", icon: Search, label: "Market Scanner" },
  { to: "/intelligence", icon: Brain, label: "Intelligence" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

const STATUS_COLOR: Record<string, string> = {
  idle: "bg-gray-500",
  analyzing: "bg-accent-blue",
  executing: "bg-accent-green",
  learning: "bg-accent-yellow",
};

export default function Sidebar() {
  const { wsConnected, agentStatus } = useOkaneStore();

  return (
    <aside className="w-56 bg-surface-card border-r border-surface-border flex flex-col">
      {/* Logo */}
      <div className="p-4 border-b border-surface-border">
        <h1 className="text-xl font-bold text-white font-mono">
          <span className="text-accent-green">¥</span> okane
        </h1>
        <p className="text-xs text-gray-500 mt-0.5">Kalshi Paper Agent</p>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-3 space-y-1">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                isActive
                  ? "bg-accent-blue/20 text-accent-blue"
                  : "text-gray-400 hover:text-white hover:bg-white/5"
              )
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Status footer */}
      <div className="p-3 border-t border-surface-border space-y-2">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span
            className={clsx(
              "w-2 h-2 rounded-full",
              wsConnected ? "bg-accent-green animate-pulse" : "bg-red-500"
            )}
          />
          {wsConnected ? "Live" : "Disconnected"}
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Activity size={12} />
          <span>
            Agent:{" "}
            <span className="text-white capitalize">{agentStatus}</span>
          </span>
        </div>
      </div>
    </aside>
  );
}
