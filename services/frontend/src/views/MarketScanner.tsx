import { useOkaneStore } from "../store";

export default function MarketScanner() {
  const markets = useOkaneStore((s) => s.markets);
  const recentSignals = useOkaneStore((s) => s.recentSignals);

  const marketList = Array.from(markets.values())
    .sort((a, b) => (b.volume ?? 0) - (a.volume ?? 0))
    .slice(0, 50);

  return (
    <div className="p-6 space-y-5">
      <h2 className="text-lg font-semibold text-white">Market Scanner</h2>

      {recentSignals.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-400 mb-3">Recent Signals</h3>
          <div className="space-y-2">
            {recentSignals.slice(0, 5).map((sig, i) => (
              <div key={i} className="bg-surface-card border border-surface-border rounded-lg p-3 flex items-center gap-4 text-sm">
                <span className="font-mono text-xs text-gray-400 w-32 truncate">{sig.market_ticker}</span>
                <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase ${sig.side === "yes" ? "bg-accent-green/20 text-accent-green" : "bg-accent-red/20 text-accent-red"}`}>
                  {sig.side}
                </span>
                <span className="text-gray-500 text-xs">{sig.strategy}</span>
                <span className="text-white font-mono text-xs">{(sig.confidence * 100).toFixed(0)}%</span>
                <span className="text-gray-500 text-xs truncate flex-1">{sig.reasoning_preview}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <h3 className="text-sm font-medium text-gray-400 mb-3">
          Active Markets ({marketList.length})
        </h3>
        <div className="bg-surface-card rounded-xl border border-surface-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border">
                {["Ticker", "YES Bid", "YES Ask", "Last", "Volume", "Status"].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-xs text-gray-500 uppercase tracking-wider font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {marketList.map((mkt) => (
                <tr key={mkt.ticker} className="border-b border-surface-border/50 hover:bg-white/5">
                  <td className="px-4 py-2 font-mono text-xs text-gray-300">{mkt.ticker}</td>
                  <td className="px-4 py-2 font-mono text-xs">{mkt.yes_bid != null ? `$${mkt.yes_bid.toFixed(3)}` : "—"}</td>
                  <td className="px-4 py-2 font-mono text-xs">{mkt.yes_ask != null ? `$${mkt.yes_ask.toFixed(3)}` : "—"}</td>
                  <td className="px-4 py-2 font-mono text-xs">{mkt.last_price != null ? `$${mkt.last_price.toFixed(3)}` : "—"}</td>
                  <td className="px-4 py-2 font-mono text-xs">{mkt.volume?.toLocaleString() ?? "—"}</td>
                  <td className="px-4 py-2 text-xs text-gray-500 capitalize">{mkt.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
