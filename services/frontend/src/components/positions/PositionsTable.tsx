import clsx from "clsx";
import type { Position } from "../../types";
import { kalshiUrl, betDescription } from "../../utils/kalshi";

interface Props {
  positions: Position[];
  markets?: Map<string, { yes_bid?: number | null; last_price?: number | null }>;
}

export default function PositionsTable({ positions, markets }: Props) {
  if (positions.length === 0) {
    return (
      <div className="bg-surface-card rounded-xl border border-surface-border p-8 text-center text-gray-500 text-sm">
        No positions
      </div>
    );
  }

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border">
              {["Market", "Bet", "Contracts", "Entry", "Cost", "Current", "Unreal. P&L", "Opened"].map((h) => (
                <th key={h} className="text-left px-4 py-3 text-xs text-gray-500 uppercase tracking-wider font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => {
              const mkt = markets?.get(pos.market_ticker);
              const currentPrice = mkt?.yes_bid ?? mkt?.last_price ?? pos.entry_price;
              const unrealized =
                pos.side === "yes"
                  ? pos.contracts * (currentPrice - pos.entry_price)
                  : pos.contracts * ((1 - pos.entry_price) - (1 - currentPrice));
              const isPositive = unrealized >= 0;

              return (
                <tr key={pos.id} className="border-b border-surface-border/50 hover:bg-white/5 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs">
                    <a
                      href={kalshiUrl(pos.market_ticker)}
                      target="_blank"
                      rel="noreferrer"
                      className="text-accent-blue hover:underline"
                    >
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
                  <td className="px-4 py-3 font-mono text-gray-400">${(pos.contracts * pos.entry_price).toFixed(2)}</td>
                  <td className="px-4 py-3 font-mono">${currentPrice.toFixed(3)}</td>
                  <td className={clsx("px-4 py-3 font-mono font-medium", isPositive ? "text-accent-green" : "text-accent-red")}>
                    {isPositive ? "+" : ""}${unrealized.toFixed(2)}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {new Date(pos.opened_at).toLocaleDateString()}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
