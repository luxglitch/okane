"use strict";

const { WebSocketServer, WebSocket } = require("ws");
const { randomUUID } = require("crypto");
const log = require("./logger");

class WSRelay {
  constructor(port) {
    this.port = port;
    this.wss = new WebSocketServer({ port });
    // Map of clientId → { ws, subscriptions: Set<string> }
    this.clients = new Map();

    this.wss.on("connection", (ws, req) => this._onConnect(ws, req));
    this.wss.on("error", (err) => log.error({ err }, "ws_server_error"));

    log.info({ port }, "ws_relay_listening");
  }

  _onConnect(ws, req) {
    const clientId = randomUUID();
    this.clients.set(clientId, { ws, subscriptions: new Set() });
    log.info({ clientId, ip: req.socket.remoteAddress }, "ws_client_connected");

    ws.on("message", (data) => {
      try {
        const msg = JSON.parse(data.toString());
        this._handleClientMessage(clientId, ws, msg);
      } catch (err) {
        log.warn({ clientId, err: err.message }, "ws_invalid_message");
      }
    });

    ws.on("close", () => {
      this.clients.delete(clientId);
      log.info({ clientId }, "ws_client_disconnected");
    });

    ws.on("error", (err) => {
      log.warn({ clientId, err: err.message }, "ws_client_error");
      this.clients.delete(clientId);
    });

    // Send a welcome message
    this._send(ws, { type: "connected", data: { clientId } });
  }

  _handleClientMessage(clientId, ws, msg) {
    const client = this.clients.get(clientId);
    if (!client) return;

    switch (msg.type) {
      case "subscribe":
        if (Array.isArray(msg.topics)) {
          msg.topics.forEach((t) => client.subscriptions.add(t));
          log.debug({ clientId, topics: msg.topics }, "ws_subscribed");
        }
        break;

      case "unsubscribe":
        if (Array.isArray(msg.topics)) {
          msg.topics.forEach((t) => client.subscriptions.delete(t));
        }
        break;

      case "ping":
        this._send(ws, { type: "pong", data: {} });
        break;

      default:
        log.debug({ clientId, type: msg.type }, "ws_unknown_message_type");
    }
  }

  broadcast(type, data) {
    const envelope = JSON.stringify({ type, ts: new Date().toISOString(), data });
    let delivered = 0;

    for (const [clientId, client] of this.clients.entries()) {
      if (client.ws.readyState !== WebSocket.OPEN) continue;
      // Send if client has no subscriptions (receives all) or is subscribed to this type
      if (client.subscriptions.size === 0 || client.subscriptions.has(type)) {
        try {
          client.ws.send(envelope);
          delivered++;
        } catch (err) {
          log.warn({ clientId, err: err.message }, "ws_send_error");
          this.clients.delete(clientId);
        }
      }
    }

    return delivered;
  }

  _send(ws, payload) {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ ...payload, ts: new Date().toISOString() }));
    }
  }

  get clientCount() {
    return this.clients.size;
  }
}

module.exports = WSRelay;
