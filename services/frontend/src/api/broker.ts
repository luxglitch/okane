import type { Portfolio, PortfolioSnapshot, Position } from "../types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface WarmupStatus {
  market_count: number;
  median_snapshots: number;
  overall_pct: number;
  eta_seconds: number;
  strategies: Record<string, { threshold: number; markets_ready: number; markets_total: number; pct: number; ready: boolean }>;
}

export const api = {
  getWarmup: () => get<WarmupStatus>("/warmup"),
  getPortfolio: () => get<Portfolio>("/portfolio"),
  getPortfolioHistory: (interval = "1h", limit = 200) =>
    get<PortfolioSnapshot[]>(`/portfolio/history?interval=${interval}&limit=${limit}`),
  getPositions: (status?: string) =>
    get<Position[]>(`/positions${status ? `?status=${status}` : ""}`),
  getPosition: (id: string) => get<Position>(`/positions/${id}`),
};
