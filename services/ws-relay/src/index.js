"use strict";

const Redis = require("ioredis");
const WSRelay = require("./websocket");
const { REDIS_TO_WS_TYPE, ALL_CHANNELS } = require("./channels");
const log = require("./logger");

const REDIS_URL = process.env.REDIS_URL || "redis://redis:6379/0";
const WS_PORT = parseInt(process.env.WS_PORT || "3001", 10);

async function main() {
  log.info({ redisUrl: REDIS_URL, wsPort: WS_PORT }, "ws_relay_starting");

  // WebSocket server
  const relay = new WSRelay(WS_PORT);

  // Redis subscriber (separate connection — can't use subscriber for other commands)
  const subscriber = new Redis(REDIS_URL, {
    retryStrategy(times) {
      const delay = Math.min(times * 200, 5000);
      log.warn({ attempt: times, delayMs: delay }, "redis_reconnecting");
      return delay;
    },
  });

  subscriber.on("error", (err) => log.error({ err }, "redis_error"));
  subscriber.on("connect", () => log.info("redis_connected"));
  subscriber.on("ready", async () => {
    log.info({ channels: ALL_CHANNELS }, "redis_subscribing");
    await subscriber.subscribe(...ALL_CHANNELS);
  });

  subscriber.on("message", (channel, message) => {
    const wsType = REDIS_TO_WS_TYPE[channel];
    if (!wsType) return;

    let data;
    try {
      data = JSON.parse(message);
    } catch {
      data = { raw: message };
    }

    const delivered = relay.broadcast(wsType, data);
    log.debug({ channel, wsType, delivered, clients: relay.clientCount }, "message_broadcast");
  });

  // Heartbeat: broadcast client count every 30s
  setInterval(() => {
    relay.broadcast("heartbeat", { clients: relay.clientCount, ts: new Date().toISOString() });
  }, 30_000);

  // Graceful shutdown
  const shutdown = async (sig) => {
    log.info({ sig }, "ws_relay_shutting_down");
    subscriber.disconnect();
    process.exit(0);
  };
  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));
}

main().catch((err) => {
  log.error({ err }, "fatal_error");
  process.exit(1);
});
