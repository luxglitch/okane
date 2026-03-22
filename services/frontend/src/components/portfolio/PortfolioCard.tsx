import clsx from "clsx";
import type { Portfolio } from "../../types";

interface Props {
  portfolio: Portfolio | null;
}

function Stat({
  label,
  value,
  sub,
  positive,
}: {
  label: string;
  value: string;
  sub?: string;
  positive?: boolean;
}) {
  return (
    <div>
      <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
      <p
        className={clsx(
          "text-xl font-bold font-mono mt-0.5",
          positive === true && "text-accent-green",
          positive === false && "text-accent-red",
          positive === undefined && "text-white"
        )}
      >
        {value}
      </p>
      {sub && <p className="text-xs text-gray-500">{sub}</p>}
    </div>
  );
}

export default function PortfolioCard({ portfolio }: Props) {
  if (!portfolio) {
    return (
      <div className="bg-surface-card rounded-xl border border-surface-border p-5 animate-pulse h-28" />
    );
  }

  const pnl = portfolio.total_value - portfolio.starting_balance;
  const pnlPositive = pnl >= 0;

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-5">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
        <Stat
          label="Portfolio Value"
          value={`$${portfolio.total_value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
        />
        <Stat
          label="Total P&L"
          value={`${pnlPositive ? "+" : ""}$${pnl.toFixed(2)}`}
          sub={`${portfolio.pnl_percent >= 0 ? "+" : ""}${portfolio.pnl_percent.toFixed(2)}%`}
          positive={pnlPositive}
        />
        <Stat
          label="Cash"
          value={`$${portfolio.cash.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          sub={`${((portfolio.cash / portfolio.total_value) * 100).toFixed(0)}% of portfolio`}
        />
        <Stat
          label="Open Positions"
          value={String(portfolio.open_positions)}
          sub={`$${portfolio.positions_value.toFixed(2)} invested`}
        />
      </div>
    </div>
  );
}
