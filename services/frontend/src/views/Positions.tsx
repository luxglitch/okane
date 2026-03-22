import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/broker";
import PositionsTable from "../components/positions/PositionsTable";
import { useOkaneStore } from "../store";

export default function Positions() {
  const [tab, setTab] = useState<"open" | "closed">("open");
  const markets = useOkaneStore((s) => s.markets);

  const { data: positions = [] } = useQuery({
    queryKey: ["positions", tab],
    queryFn: () => api.getPositions(tab),
    refetchInterval: 10_000,
  });

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Positions</h2>
        <div className="flex gap-2">
          {(["open", "closed"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-1.5 rounded-lg text-sm capitalize transition-colors ${
                tab === t
                  ? "bg-accent-blue/20 text-accent-blue"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      <PositionsTable positions={positions} markets={tab === "open" ? markets : undefined} />
    </div>
  );
}
