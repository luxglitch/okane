import { useOkaneStore } from "../../store";
import type { FeedEvent } from "../../types";
import clsx from "clsx";

const TAG_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
  observation: { icon: "🔍", color: "text-blue-400", label: "Scanning" },
  hypothesis: { icon: "📊", color: "text-purple-400", label: "Analyzing" },
  decision: { icon: "✅", color: "text-accent-green", label: "Decision" },
  reflection: { icon: "📚", color: "text-accent-yellow", label: "Learning" },
  error: { icon: "⚠️", color: "text-accent-red", label: "Error" },
  info: { icon: "💡", color: "text-gray-400", label: "Info" },
  agent_signal: { icon: "💡", color: "text-accent-blue", label: "Signal" },
  position_fill: { icon: "✅", color: "text-accent-green", label: "Trade Entered" },
  position_close: { icon: "🔒", color: "text-gray-300", label: "Trade Closed" },
  market_settlement: { icon: "🏁", color: "text-accent-yellow", label: "Settlement" },
  system_alert: { icon: "🚨", color: "text-accent-red", label: "Alert" },
};

function getEventContent(event: FeedEvent): { icon: string; color: string; label: string; body: string } {
  if (event.type === "agent_thought") {
    const d = event.data as { type?: string; content?: string; ticker?: string };
    const cfg = TAG_CONFIG[d.type ?? "info"] ?? TAG_CONFIG.info;
    return { ...cfg, body: d.content ?? "" };
  }
  if (event.type === "agent_signal") {
    const d = event.data as { market_ticker?: string; side?: string; confidence?: number; strategy?: string };
    return {
      ...TAG_CONFIG.agent_signal,
      body: `${d.market_ticker} ${(d.side ?? "").toUpperCase()} [${d.strategy}] confidence=${((d.confidence ?? 0) * 100).toFixed(0)}%`,
    };
  }
  if (event.type === "position_fill") {
    const d = event.data as { market_ticker?: string; side?: string; contracts?: number; fill_price?: number };
    return {
      ...TAG_CONFIG.position_fill,
      body: `${d.market_ticker} — ${d.side?.toUpperCase()} x${d.contracts} @ $${d.fill_price?.toFixed(3)}`,
    };
  }
  if (event.type === "position_close") {
    const d = event.data as { market_ticker?: string; pnl?: number };
    return {
      ...TAG_CONFIG.position_close,
      body: `${d.market_ticker} closed — P&L: ${(d.pnl ?? 0) >= 0 ? "+" : ""}$${(d.pnl ?? 0).toFixed(2)}`,
    };
  }
  if (event.type === "market_settlement") {
    const d = event.data as { ticker?: string; result?: string };
    return {
      ...TAG_CONFIG.market_settlement,
      body: `${d.ticker} resolved ${d.result?.toUpperCase()}`,
    };
  }
  if (event.type === "system_alert") {
    const d = event.data as { message?: string };
    return { ...TAG_CONFIG.system_alert, body: d.message ?? "System alert" };
  }
  return { icon: "•", color: "text-gray-500", label: event.type, body: JSON.stringify(event.data).slice(0, 80) };
}

function FeedRow({ event }: { event: FeedEvent }) {
  const { icon, color, label, body } = getEventContent(event);
  const time = new Date(event.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  return (
    <div className="flex gap-2 py-1.5 border-b border-surface-border/50 last:border-0 font-mono text-xs">
      <span className="text-gray-600 shrink-0 w-20">{time}</span>
      <span className={clsx("shrink-0 w-5")}>{icon}</span>
      <span className={clsx("shrink-0 w-24 font-medium", color)}>{label}</span>
      <span className="text-gray-300 truncate">{body}</span>
    </div>
  );
}

export default function LiveFeed() {
  const feedEvents = useOkaneStore((s) =>
    s.feedEvents.filter(
      (e) =>
        e.type === "agent_thought" ||
        e.type === "agent_signal" ||
        e.type === "position_fill" ||
        e.type === "position_close" ||
        e.type === "market_settlement" ||
        e.type === "system_alert"
    )
  );

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4 h-80 overflow-hidden">
      <h3 className="text-sm font-medium text-gray-400 mb-3">Live Activity Feed</h3>
      <div className="overflow-y-auto h-64 space-y-0 scrollbar-thin">
        {feedEvents.length === 0 ? (
          <p className="text-gray-600 text-xs font-mono">Waiting for agent activity…</p>
        ) : (
          feedEvents.map((e) => <FeedRow key={e.id} event={e} />)
        )}
      </div>
    </div>
  );
}
