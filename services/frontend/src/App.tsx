import { Routes, Route } from "react-router-dom";
import Sidebar from "./components/layout/Sidebar";
import Dashboard from "./views/Dashboard";
import Positions from "./views/Positions";
import TradeHistory from "./views/TradeHistory";
import MarketScanner from "./views/MarketScanner";
import Intelligence from "./views/Intelligence";
import Settings from "./views/Settings";
import { useWebSocket } from "./hooks/useWebSocket";

export default function App() {
  useWebSocket();

  return (
    <div className="flex h-screen bg-surface text-white overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/positions" element={<Positions />} />
          <Route path="/history" element={<TradeHistory />} />
          <Route path="/scanner" element={<MarketScanner />} />
          <Route path="/intelligence" element={<Intelligence />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
