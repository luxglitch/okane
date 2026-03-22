# Okane — Autonomous Kalshi Paper Trading Agent

> **⚠ WORK IN PROGRESS — DO NOT USE WITH REAL MONEY**
>
> This project is experimental and under active development. Strategies are
> unproven, logic bugs exist and are being found regularly, and nothing here
> has been audited for financial soundness. It is a paper-trading research
> tool only. Do not connect it to a live Kalshi account or treat any of its
> signals, valuations, or outputs as financial advice.

A fully autonomous, self-learning prediction market trading agent that simulates trades on [Kalshi.com](https://kalshi.com) using paper money. The system learns from its own wins and losses and surfaces all activity through a real-time dashboard.

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Docker | ≥ 24 | [Install](https://docs.docker.com/get-docker/) |
| Docker Compose | v2 | Included with Docker Desktop |
| Kalshi account | — | API key from developer portal |
| Anthropic API key | — | For Claude LLM integration |

---

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url>
cd okane

# 2. Bootstrap (copies .env.example, builds images, starts services)
./scripts/bootstrap.sh

# 3. That's it — dashboard is at http://localhost
```

**Within 60 seconds:** Live Kalshi market data is being fetched and stored.
**Within 5 minutes:** The agent analyzes markets and enters its first paper trade.
**Immediately:** Dashboard is at `http://localhost`, Grafana at `http://localhost/grafana`.

---

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────────────┐
│  Kalshi API │────▶│  kalshi-fetcher                              │
└─────────────┘     │  • RSA-signed REST polling                   │
                    │  • Circuit breaker + exponential backoff      │
                    └──────────┬────────────────────────┬───────────┘
                               │ TimescaleDB             │ Redis
                    ┌──────────▼───────────┐   ┌────────▼────────┐
                    │  agent-core          │   │  ws-relay       │
                    │  • 4 strategies      │   │  • Redis → WS   │
                    │  • Kelly sizing      │   └────────┬────────┘
                    │  • LLM enhancement   │            │ WebSocket
                    │  • ChromaDB RAG      │   ┌────────▼────────┐
                    │  • Optuna tuning     │   │  frontend       │
                    └──────────┬───────────┘   │  • React + Vite │
                               │ REST API       │  • Real-time    │
                    ┌──────────▼───────────┐   └─────────────────┘
                    │  paper-broker        │
                    │  • FastAPI           │
                    │  • $10k paper wallet │
                    │  • Slippage model    │
                    └──────────────────────┘
```

**Services:**

| Service | Description | Port |
|---|---|---|
| `kalshi-fetcher` | Polls Kalshi REST API, stores to TimescaleDB | — |
| `agent-core` | Multi-strategy AI agent with self-learning | — |
| `paper-broker` | Virtual portfolio management (FastAPI) | 8001 (internal) |
| `ws-relay` | Redis Pub/Sub → WebSocket bridge | 3001 (internal) |
| `frontend` | React dashboard | 80 (via nginx) |
| `nginx` | Reverse proxy | **80** (host) |
| `postgres` | TimescaleDB | 5432 (internal) |
| `chromadb` | Vector store for RAG | 8000 (internal) |
| `redis` | Event bus + caching | 6379 (internal) |
| `prometheus` | Metrics collection | 9090 (internal) |
| `grafana` | Monitoring dashboards | `/grafana` |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `KALSHI_API_KEY_ID` | Yes | Kalshi developer portal key ID |
| `KALSHI_PRIVATE_KEY_B64` | Yes | RSA private key, base64-encoded (`base64 -w 0 key.pem`) |
| `KALSHI_BASE_URL` | No | Default: live API. Set to demo URL for testing |
| `ANTHROPIC_API_KEY` | Yes | For LLM signal enhancement and post-mortems |
| `POSTGRES_PASSWORD` | Yes | Strong password for the DB |
| `GRAFANA_ADMIN_PASSWORD` | Yes | Grafana admin login |
| `FETCH_INTERVAL_SECONDS` | No | Default: 30 |
| `AGENT_CYCLE_SECONDS` | No | Default: 60 |
| `MIN_SIGNAL_CONFIDENCE` | No | Default: 0.65 |
| `MAX_POSITION_FRACTION` | No | Default: 0.05 (5% per trade) |

---

## Kalshi API Authentication

Kalshi uses RSA request signing, not a simple bearer token.

1. Create an API key in the Kalshi developer portal
2. Download the RSA private key PEM file
3. Base64-encode it: `base64 -w 0 your_key.pem` (Linux) or `base64 -i your_key.pem` (macOS)
4. Paste the result as `KALSHI_PRIVATE_KEY_B64` in `.env`

---

## Development

### Running individual services locally

```bash
# Install uv (Python)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Run kalshi-fetcher locally
cd services/kalshi-fetcher
uv sync
uv run python -m src.main

# Run paper-broker locally
cd services/paper-broker
uv sync
uv run python -m src.main

# Run frontend dev server (with proxy to local services)
cd services/frontend
npm install
npm run dev
```

### Viewing logs

```bash
./scripts/logs.sh               # all services
./scripts/logs.sh agent-core    # just the agent
./scripts/logs.sh kalshi-fetcher
```

### Resetting paper portfolio

```bash
./scripts/reset-paper.sh
```

---

## Agent Strategies

The agent runs 4 strategies in parallel every cycle:

| Strategy | Technique | LLM? |
|---|---|---|
| `sentiment` | Keyword scoring on market titles | Optional |
| `stat_arb` | Z-score mean reversion | No |
| `momentum` | RSI(14) + trend detection | No |
| `pattern` | ChromaDB RAG: similar historical patterns | No |

Signals are ranked by `confidence × strategy_weight`, top 3 are LLM-enhanced, then risk-checked and sized using fractional Kelly Criterion (1/4 Kelly, max 5% of portfolio).

### Adding a new strategy

1. Create `services/agent-core/src/strategies/my_strategy.py`
2. Inherit from `BaseStrategy`, implement `analyze()` and optionally `warmup()`
3. Add it to the `strategies` list in `services/agent-core/src/main.py`
4. Insert a default weight row in `agent_weights` table

---

## Paper Broker API

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/portfolio` | GET | Current portfolio snapshot |
| `/portfolio/history` | GET | Time series (supports `?interval=5m\|1h\|4h\|1d`) |
| `/positions` | GET | List positions (`?status=open\|closed`) |
| `/positions/{id}` | GET | Single position |
| `/orders` | POST | Place a paper trade |
| `/orders/{id}` | DELETE | Close a position (requires `?exit_price=0.xx`) |

---

## Monitoring

Access Grafana at `http://localhost/grafana` (admin password from `.env`).

Prometheus scrapes:
- `paper-broker:8001/metrics` — portfolio value, order counts
- `agent-core:9090/metrics` — signals, cycle time, LLM costs
- `kalshi-fetcher:9090/metrics` — fetch rate, API errors

---

## Known Limitations

- **Paper trading only** — no real money is used or at risk
- **Kalshi API rate limits** — the fetcher respects these with exponential backoff, but extremely high polling frequencies may trigger throttling
- **LLM cost cap** — default 200 LLM calls/day; adjust `LLM_MAX_CALLS_PER_DAY` in `.env`
- **Pattern strategy cold start** — the ChromaDB pattern store is empty until markets settle and post-mortems run; expect 0 pattern signals initially
- **No orderbook data in paper broker** — slippage is modeled analytically, not from live books

---

## License

MIT
