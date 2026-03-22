export interface Portfolio {
  cash: number;
  positions_value: number;
  total_value: number;
  realized_pnl: number;
  unrealized_pnl: number;
  pnl_percent: number;
  open_positions: number;
  starting_balance: number;
}

export interface PortfolioSnapshot {
  ts: string;
  cash: number;
  positions_value: number;
  total_value: number;
  open_positions: number;
  realized_pnl: number;
  unrealized_pnl: number;
}

export interface Position {
  id: string;
  opened_at: string;
  closed_at: string | null;
  market_ticker: string;
  side: "yes" | "no";
  contracts: number;
  entry_price: number;
  exit_price: number | null;
  slippage_paid: number;
  fees_paid: number;
  pnl: number | null;
  status: "open" | "closed" | "expired";
  close_reason: string | null;
  unrealized_pnl?: number;
}

export interface MarketSnapshot {
  ticker: string;
  yes_bid: number | null;
  yes_ask: number | null;
  no_bid: number | null;
  no_ask: number | null;
  last_price: number | null;
  volume: number;
  open_interest: number;
  status: string;
  ts: string;
}

export interface AgentSignal {
  market_ticker: string;
  strategy: string;
  confidence: number;
  side: "yes" | "no";
  reasoning_preview: string;
  ts: string;
}

export interface AgentThought {
  type: string;
  content: string;
  ticker: string | null;
  ts: string;
}

export type FeedEventType =
  | "market_update"
  | "portfolio_snapshot"
  | "position_fill"
  | "position_close"
  | "agent_signal"
  | "agent_thought"
  | "market_settlement"
  | "system_alert"
  | "heartbeat"
  | "connected";

export interface FeedEvent {
  id: string;
  type: FeedEventType;
  ts: string;
  data: Record<string, unknown>;
}

export interface WSMessage {
  type: FeedEventType;
  ts: string;
  data: Record<string, unknown>;
}
