import { useOkaneStore } from "../store";

export default function Intelligence() {
  const thoughts = useOkaneStore((s) => s.agentThoughts);
  const signals = useOkaneStore((s) => s.recentSignals);

  const strategyStats = signals.reduce<Record<string, { count: number; avg: number }>>((acc, sig) => {
    if (!acc[sig.strategy]) acc[sig.strategy] = { count: 0, avg: 0 };
    acc[sig.strategy].count++;
    acc[sig.strategy].avg = (acc[sig.strategy].avg + sig.confidence) / acc[sig.strategy].count;
    return acc;
  }, {});

  return (
    <div className="p-6 space-y-5">
      <h2 className="text-lg font-semibold text-white">Agent Intelligence</h2>

      {/* Strategy performance */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Object.entries(strategyStats).map(([name, stats]) => (
          <div key={name} className="bg-surface-card border border-surface-border rounded-xl p-4">
            <p className="text-xs text-gray-500 uppercase">{name}</p>
            <p className="text-2xl font-bold font-mono text-white mt-1">{stats.count}</p>
            <p className="text-xs text-gray-500">signals · avg {(stats.avg * 100).toFixed(0)}%</p>
          </div>
        ))}
        {Object.keys(strategyStats).length === 0 && (
          <div className="col-span-4 bg-surface-card border border-surface-border rounded-xl p-6 text-center text-gray-500 text-sm">
            No signals received yet — agent is warming up
          </div>
        )}
      </div>

      {/* Reasoning trace */}
      <div>
        <h3 className="text-sm font-medium text-gray-400 mb-3">Agent Reasoning Trace</h3>
        <div className="bg-surface-card border border-surface-border rounded-xl p-4 h-96 overflow-y-auto font-mono text-xs space-y-1">
          {thoughts.length === 0 ? (
            <p className="text-gray-600">No thoughts yet…</p>
          ) : (
            thoughts.map((t, i) => (
              <div key={i} className="flex gap-3 py-0.5 border-b border-surface-border/30">
                <span className="text-gray-600 w-20 shrink-0">
                  {new Date(t.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </span>
                <span className="text-gray-500 w-20 shrink-0">[{t.type}]</span>
                <span className="text-gray-300">{t.content}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
