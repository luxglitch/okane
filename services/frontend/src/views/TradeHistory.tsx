import { useQuery } from "@tanstack/react-query";
import { api } from "../api/broker";
import clsx from "clsx";
import { kalshiUrl, betDescription } from "../utils/kalshi";

export default function TradeHistory() {
  const { data: positions = [] } = useQuery({
    queryKey: ["positions", "closed"],
    queryFn: () => api.getPositions("closed"),
    refetchInterval: 30_000,
  });

  return (
    <div className="p-6 space-y-4">
      <h2 className="text-lg font-semibold text-white">Trade History</h2>

      {positions.length === 0 ? (
        <div className="bg-surface-card rounded-xl border border-surface-border p-8 text-center text-gray-500 text-sm">
          No closed trades yet
        </div>
      ) : (
        <div className="bg-surface-card rounded-xl border border-surface-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border">
                {["Market", "Bet", "Contracts", "Entry", "Exit", "P&L", "Close Reason", "Closed"].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-xs text-gray-500 uppercase tracking-wider font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {positions.map((pos) => {
                const pnl = pos.pnl ?? 0;
                const isWin = pnl > 0;
                return (
                  <tr key={pos.id} className="border-b border-surface-border/50 hover:bg-white/5 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs">
                      <a href={kalshiUrl(pos.market_ticker)} target="_blank" rel="noreferrer"
                        className="text-accent-blue hover:underline">
                        {pos.market_ticker}
                      </a>
                    </td>
                    <td className="px-4 py-3 text-sm whitespace-nowrap">
                      <span className={clsx(
                        "font-semibold",
                        pos.side === "yes" ? "text-accent-green" : "text-accent-red"
                      )}>
                        {betDescription(pos.market_ticker, pos.side)}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono">{pos.contracts}</td>
                    <td className="px-4 py-3 font-mono">${pos.entry_price.toFixed(3)}</td>
                    <td className="px-4 py-3 font-mono">${(pos.exit_price ?? 0).toFixed(3)}</td>
                    <td className={clsx("px-4 py-3 font-mono font-medium", isWin ? "text-accent-green" : "text-accent-red")}>
                      {isWin ? "+" : ""}${pnl.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500 capitalize">{pos.close_reason ?? "—"}</td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {pos.closed_at ? new Date(pos.closed_at).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
