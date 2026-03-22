import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useOkaneStore } from "../../store";
import type { PortfolioSnapshot } from "../../types";

function fmt(v: number) {
  return `$${v.toLocaleString("en-US", { minimumFractionDigits: 0 })}`;
}

function fmtTime(ts: string) {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

interface Props {
  initialHistory: PortfolioSnapshot[];
}

export default function PnLChart({ initialHistory }: Props) {
  const liveHistory = useOkaneStore((s) => s.portfolioHistory);
  const data = liveHistory.length > 0 ? liveHistory : initialHistory;

  if (data.length < 1) {
    return (
      <div className="bg-surface-card rounded-xl border border-surface-border p-5 flex items-center justify-center h-48 text-gray-500 text-sm">
        Waiting for portfolio data…
      </div>
    );
  }

  const starting = data[0]?.total_value ?? 10000;

  const chartData = data.map((d) => ({
    ts: d.ts,
    value: d.total_value,
    pnl: d.total_value - starting,
  }));

  const isPositive = chartData[chartData.length - 1]?.pnl >= 0;
  const color = isPositive ? "#00d4aa" : "#ff4d6d";

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-5">
      <h3 className="text-sm font-medium text-gray-400 mb-3">Portfolio Value</h3>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={chartData} margin={{ top: 5, right: 10, bottom: 0, left: 10 }}>
          <defs>
            <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.25} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="ts"
            tickFormatter={fmtTime}
            tick={{ fontSize: 10, fill: "#6b7280" }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tickFormatter={fmt}
            tick={{ fontSize: 10, fill: "#6b7280" }}
            tickLine={false}
            axisLine={false}
            width={72}
          />
          <Tooltip
            formatter={(v: number) => [fmt(v), "Portfolio"]}
            labelFormatter={fmtTime}
            contentStyle={{
              background: "#1a1d27",
              border: "1px solid #2a2d3a",
              borderRadius: 8,
              fontSize: 12,
            }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            fill="url(#pnlGrad)"
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
