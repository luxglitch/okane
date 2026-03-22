"use strict";

// Maps Redis pub/sub channels to WebSocket message types.
// Services publish to Redis channels; ws-relay rebroadcasts as typed WS messages.

const REDIS_TO_WS_TYPE = {
  "okane:market:update": "market_update",
  "okane:market:settlement": "market_settlement",
  "okane:portfolio:snapshot": "portfolio_snapshot",
  "okane:position:fill": "position_fill",
  "okane:position:close": "position_close",
  "okane:agent:signal": "agent_signal",
  "okane:agent:thought": "agent_thought",
  "okane:agent:weights": "agent_weights",
  "okane:system:alert": "system_alert",
};

const ALL_CHANNELS = Object.keys(REDIS_TO_WS_TYPE);

module.exports = { REDIS_TO_WS_TYPE, ALL_CHANNELS };
