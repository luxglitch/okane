import { useQuery } from "@tanstack/react-query";
import { api } from "../api/broker";
import PortfolioCard from "../components/portfolio/PortfolioCard";
import PnLChart from "../components/portfolio/PnLChart";
import LiveFeed from "../components/feed/LiveFeed";
import PositionsTable from "../components/positions/PositionsTable";
import { useOkaneStore } from "../store";

function WarmupBanner() {
  const { data: warmup } = useQuery({
    queryKey: ["warmup"],
    queryFn: api.getWarmup,
    refetchInterval: 15_000,
  });

  if (!warmup || warmup.overall_pct >= 100) return null;

  const etaMin = Math.ceil(warmup.eta_seconds / 60);
  const strategies = Object.entries(warmup.strategies);

  return (
    <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-yellow-400 text-sm font-medium">⏳ Agent Warming Up</span>
          <span className="text-gray-400 text-xs">
            {warmup.market_count} markets · {warmup.median_snapshots} snapshots/market median
          </span>
        </div>
        <span className="text-yellow-300 text-sm font-mono">
          {warmup.overall_pct}% · ~{etaMin}m remaining
        </span>
      </div>

      <div className="w-full bg-gray-700 rounded-full h-2">
        <div
          className="bg-yellow-400 h-2 rounded-full transition-all duration-500"
          style={{ width: `${warmup.overall_pct}%` }}
        />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {strategies.map(([name, s]) => (
          <div key={name} className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${s.ready ? "bg-green-400" : "bg-yellow-400"}`} />
            <span className="text-xs text-gray-300 capitalize">{name}</span>
            <span className="text-xs text-gray-500 ml-auto">{s.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const livePortfolio = useOkaneStore((s) => s.portfolio);
  const markets = useOkaneStore((s) => s.markets);
  const openPositions = useOkaneStore((s) => s.openPositions);

  const { data: portfolio } = useQuery({
    queryKey: ["portfolio"],
    queryFn: api.getPortfolio,
    refetchInterval: 10_000,
    initialData: livePortfolio ?? undefined,
  });

  const { data: history = [] } = useQuery({
    queryKey: ["portfolio-history"],
    queryFn: () => api.getPortfolioHistory("5m", 200),
    refetchInterval: 60_000,
  });

  const { data: positions = [] } = useQuery({
    queryKey: ["positions-open"],
    queryFn: () => api.getPositions("open"),
    refetchInterval: 15_000,
    initialData: openPositions.length > 0 ? openPositions : undefined,
  });

  return (
    <div className="p-6 space-y-5">
      <h2 className="text-lg font-semibold text-white">Dashboard</h2>

      <WarmupBanner />
      <PortfolioCard portfolio={portfolio ?? livePortfolio} />

      <PnLChart initialHistory={history} />
      <LiveFeed />

      <div>
        <h3 className="text-sm font-medium text-gray-400 mb-3">Open Positions</h3>
        <PositionsTable positions={positions} markets={markets} />
      </div>
    </div>
  );
}
