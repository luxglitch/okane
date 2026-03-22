import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type {
  AgentSignal,
  AgentThought,
  FeedEvent,
  MarketSnapshot,
  Portfolio,
  PortfolioSnapshot,
  Position,
  WSMessage,
} from "../types";

const MAX_FEED_EVENTS = 200;
const MAX_THOUGHTS = 100;
const MAX_SIGNALS = 50;

interface OkaneStore {
  // Connection
  wsConnected: boolean;
  agentStatus: "idle" | "analyzing" | "executing" | "learning";

  // Portfolio
  portfolio: Portfolio | null;
  portfolioHistory: PortfolioSnapshot[];

  // Positions
  openPositions: Position[];
  closedPositions: Position[];

  // Markets
  markets: Map<string, MarketSnapshot>;

  // Agent
  recentSignals: AgentSignal[];
  agentThoughts: AgentThought[];

  // Live feed
  feedEvents: FeedEvent[];

  // Actions
  setWsConnected: (connected: boolean) => void;
  setPortfolio: (portfolio: Portfolio) => void;
  setPortfolioHistory: (history: PortfolioSnapshot[]) => void;
  setPositions: (positions: Position[]) => void;
  handleWsMessage: (msg: WSMessage) => void;
}

let eventCounter = 0;

export const useOkaneStore = create<OkaneStore>()(
  persist(
    (set, get) => ({
  wsConnected: false,
  agentStatus: "idle",
  portfolio: null,
  portfolioHistory: [],
  openPositions: [],
  closedPositions: [],
  markets: new Map(),
  recentSignals: [],
  agentThoughts: [],
  feedEvents: [],

  setWsConnected: (connected) => set({ wsConnected: connected }),

  setPortfolio: (portfolio) => set({ portfolio }),

  setPortfolioHistory: (portfolioHistory) => set({ portfolioHistory }),

  setPositions: (positions) =>
    set({
      openPositions: positions.filter((p) => p.status === "open"),
      closedPositions: positions.filter((p) => p.status !== "open"),
    }),

  handleWsMessage: (msg: WSMessage) => {
    const id = `evt-${Date.now()}-${++eventCounter}`;

    // Only surface meaningful events in the feed — not raw market price ticks
    const FEED_TYPES = new Set(["agent_thought", "agent_signal", "position_fill", "position_close", "market_settlement", "system_alert"]);
    const feedEvent: FeedEvent | null = FEED_TYPES.has(msg.type)
      ? { id, type: msg.type, ts: msg.ts, data: msg.data }
      : null;

    set((state) => {
      const updates: Partial<OkaneStore> = feedEvent
        ? { feedEvents: [feedEvent, ...state.feedEvents].slice(0, MAX_FEED_EVENTS) }
        : {};

      switch (msg.type) {
        case "portfolio_snapshot": {
          const d = msg.data as Record<string, number>;
          if (state.portfolio) {
            updates.portfolio = { ...state.portfolio, ...d };
          }
          updates.portfolioHistory = [
            ...state.portfolioHistory,
            { ts: msg.ts, ...d } as PortfolioSnapshot,
          ].slice(-500);
          break;
        }

        case "market_update": {
          const snap = msg.data as unknown as MarketSnapshot;
          const newMarkets = new Map(state.markets);
          newMarkets.set(snap.ticker, snap);
          updates.markets = newMarkets;
          break;
        }

        case "position_fill": {
          // Refresh positions list on fill
          updates.agentStatus = "executing";
          break;
        }

        case "agent_signal": {
          const signal = msg.data as unknown as AgentSignal;
          updates.agentStatus = "analyzing";
          updates.recentSignals = [signal, ...state.recentSignals].slice(0, MAX_SIGNALS);
          break;
        }

        case "agent_thought": {
          const thought = msg.data as unknown as AgentThought;
          updates.agentThoughts = [thought, ...state.agentThoughts].slice(0, MAX_THOUGHTS);
          // Update agent status based on thought type
          if (thought.type === "decision") updates.agentStatus = "executing";
          else if (thought.type === "reflection") updates.agentStatus = "learning";
          else if (thought.type === "observation") updates.agentStatus = "analyzing";
          break;
        }

        case "heartbeat":
          updates.wsConnected = true;
          break;
      }

      return updates;
    });
  },
    }),
    {
      name: "okane-feed",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        feedEvents: state.feedEvents,
        agentThoughts: state.agentThoughts,
        recentSignals: state.recentSignals,
      }),
    }
  )
);
