-- =============================================================================
-- Okane Database Schema
-- TimescaleDB + PostgreSQL
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- Market Data (time-series)
-- =============================================================================

CREATE TABLE IF NOT EXISTS market_snapshots (
    ts              TIMESTAMPTZ     NOT NULL,
    market_ticker   VARCHAR(100)    NOT NULL,
    event_ticker    VARCHAR(100),
    title           TEXT,
    yes_bid         NUMERIC(6,4),
    yes_ask         NUMERIC(6,4),
    no_bid          NUMERIC(6,4),
    no_ask          NUMERIC(6,4),
    last_price      NUMERIC(6,4),
    volume          BIGINT          DEFAULT 0,
    open_interest   BIGINT          DEFAULT 0,
    liquidity       NUMERIC(12,2),
    status          VARCHAR(20),    -- 'open', 'closed', 'settled'
    close_time      TIMESTAMPTZ,
    result          VARCHAR(10),    -- 'yes', 'no', null if still open
    raw_json        JSONB
);

-- Convert to hypertable BEFORE inserting any data
SELECT create_hypertable('market_snapshots', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_market_snapshots_ticker_ts
    ON market_snapshots (market_ticker, ts DESC);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_event_ts
    ON market_snapshots (event_ticker, ts DESC);

-- =============================================================================
-- Agent Decision Records
-- =============================================================================

CREATE TABLE IF NOT EXISTS trade_signals (
    id                  UUID            DEFAULT uuid_generate_v4() PRIMARY KEY,
    ts                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    market_ticker       VARCHAR(100)    NOT NULL,
    strategy_name       VARCHAR(50),
    side                VARCHAR(3)      NOT NULL CHECK (side IN ('yes', 'no')),
    confidence          NUMERIC(5,4)    NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    raw_score           NUMERIC(8,4),
    kelly_fraction      NUMERIC(6,4),
    suggested_contracts INTEGER,
    suggested_price     NUMERIC(6,4),
    reasoning           TEXT,
    llm_enhanced        BOOLEAN         DEFAULT FALSE,
    executed            BOOLEAN         DEFAULT FALSE,
    execution_id        UUID            -- FK to positions, set after execution
);

CREATE INDEX IF NOT EXISTS idx_trade_signals_ticker_ts
    ON trade_signals (market_ticker, ts DESC);
CREATE INDEX IF NOT EXISTS idx_trade_signals_executed
    ON trade_signals (executed, ts DESC);

-- =============================================================================
-- Paper Portfolio — Positions
-- =============================================================================

CREATE TABLE IF NOT EXISTS positions (
    id              UUID            DEFAULT uuid_generate_v4() PRIMARY KEY,
    opened_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    closed_at       TIMESTAMPTZ,
    market_ticker   VARCHAR(100)    NOT NULL,
    side            VARCHAR(3)      NOT NULL CHECK (side IN ('yes', 'no')),
    contracts       INTEGER         NOT NULL CHECK (contracts > 0),
    entry_price     NUMERIC(6,4)    NOT NULL,
    exit_price      NUMERIC(6,4),
    slippage_paid   NUMERIC(8,4)    DEFAULT 0,
    fees_paid       NUMERIC(8,4)    DEFAULT 0,
    pnl             NUMERIC(12,4),
    status          VARCHAR(10)     NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'closed', 'expired')),
    signal_id       UUID            REFERENCES trade_signals(id),
    close_reason    VARCHAR(30)     -- 'target', 'stop', 'expiry', 'manual', 'settlement'
);

CREATE INDEX IF NOT EXISTS idx_positions_status
    ON positions (status, opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_positions_ticker
    ON positions (market_ticker, status);

-- =============================================================================
-- Portfolio Snapshots (time-series)
-- =============================================================================

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    ts                  TIMESTAMPTZ     NOT NULL,
    cash                NUMERIC(12,4)   NOT NULL,
    positions_value     NUMERIC(12,4)   NOT NULL DEFAULT 0,
    total_value         NUMERIC(12,4)   NOT NULL,
    open_positions      INTEGER         NOT NULL DEFAULT 0,
    realized_pnl        NUMERIC(12,4)   NOT NULL DEFAULT 0,
    unrealized_pnl      NUMERIC(12,4)   NOT NULL DEFAULT 0,
    drawdown            NUMERIC(8,4)    DEFAULT 0,
    peak_value          NUMERIC(12,4)
);

SELECT create_hypertable('portfolio_snapshots', 'ts', if_not_exists => TRUE);

-- =============================================================================
-- Market Resolution
-- =============================================================================

CREATE TABLE IF NOT EXISTS market_outcomes (
    id                  BIGSERIAL       PRIMARY KEY,
    market_ticker       VARCHAR(100)    NOT NULL UNIQUE,
    settled_at          TIMESTAMPTZ,
    result              VARCHAR(10)     NOT NULL CHECK (result IN ('yes', 'no')),
    settlement_price    NUMERIC(6,4),
    raw_json            JSONB
);

CREATE INDEX IF NOT EXISTS idx_market_outcomes_settled
    ON market_outcomes (settled_at DESC);

-- =============================================================================
-- Self-Learning: Post-mortems
-- =============================================================================

CREATE TABLE IF NOT EXISTS post_mortems (
    id              UUID            DEFAULT uuid_generate_v4() PRIMARY KEY,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    position_id     UUID            REFERENCES positions(id),
    market_ticker   VARCHAR(100),
    outcome         VARCHAR(10),    -- 'win', 'loss', 'breakeven'
    was_correct     BOOLEAN,
    pnl             NUMERIC(12,4),
    analysis        TEXT,           -- LLM-generated analysis
    lessons_learned TEXT,
    embedding_id    VARCHAR(200)    -- ChromaDB document ID
);

-- =============================================================================
-- Agent Self-Learning: Strategy Weights
-- =============================================================================

CREATE TABLE IF NOT EXISTS agent_weights (
    id              SERIAL          PRIMARY KEY,
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    strategy_name   VARCHAR(50)     NOT NULL,
    weight          NUMERIC(6,4)    NOT NULL CHECK (weight >= 0),
    trial_id        INTEGER,        -- Optuna trial ID
    optuna_value    NUMERIC(10,6),  -- objective value for this trial
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_agent_weights_active
    ON agent_weights (strategy_name, is_active, updated_at DESC);

-- Seed default weights
INSERT INTO agent_weights (strategy_name, weight, is_active) VALUES
    ('sentiment', 0.25, TRUE),
    ('stat_arb',  0.25, TRUE),
    ('momentum',  0.25, TRUE),
    ('pattern',   0.25, TRUE)
ON CONFLICT DO NOTHING;

-- =============================================================================
-- Telemetry: LLM Call Audit Log
-- =============================================================================

CREATE TABLE IF NOT EXISTS llm_calls (
    id                  UUID            DEFAULT uuid_generate_v4() PRIMARY KEY,
    ts                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    model               VARCHAR(50),
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    total_cost_usd      NUMERIC(8,6),
    purpose             VARCHAR(50),    -- 'signal_enhance', 'post_mortem', 'market_scan'
    market_ticker       VARCHAR(100),
    latency_ms          INTEGER,
    response_summary    TEXT
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_ts
    ON llm_calls (ts DESC);
CREATE INDEX IF NOT EXISTS idx_llm_calls_purpose
    ON llm_calls (purpose, ts DESC);

-- =============================================================================
-- Agent Thoughts / Reasoning Trace
-- =============================================================================

CREATE TABLE IF NOT EXISTS agent_thoughts (
    id              UUID            DEFAULT uuid_generate_v4() PRIMARY KEY,
    ts              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    thought_type    VARCHAR(30)     NOT NULL,
    -- 'observation', 'hypothesis', 'decision', 'reflection', 'error', 'info'
    market_ticker   VARCHAR(100),
    content         TEXT            NOT NULL,
    metadata        JSONB,
    duration_ms     INTEGER
);

CREATE INDEX IF NOT EXISTS idx_agent_thoughts_ts
    ON agent_thoughts (ts DESC);
CREATE INDEX IF NOT EXISTS idx_agent_thoughts_type
    ON agent_thoughts (thought_type, ts DESC);

-- =============================================================================
-- Continuous Aggregates (OHLC candlesticks)
-- =============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS market_ohlc_1min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', ts)     AS bucket,
    market_ticker,
    first(yes_bid, ts)              AS open,
    max(yes_bid)                    AS high,
    min(yes_bid)                    AS low,
    last(yes_bid, ts)               AS close,
    sum(volume)                     AS volume,
    last(open_interest, ts)         AS open_interest
FROM market_snapshots
GROUP BY bucket, market_ticker
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS market_ohlc_5min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', ts)    AS bucket,
    market_ticker,
    first(yes_bid, ts)              AS open,
    max(yes_bid)                    AS high,
    min(yes_bid)                    AS low,
    last(yes_bid, ts)               AS close,
    sum(volume)                     AS volume,
    last(open_interest, ts)         AS open_interest
FROM market_snapshots
GROUP BY bucket, market_ticker
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS market_ohlc_1hour
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', ts)       AS bucket,
    market_ticker,
    first(yes_bid, ts)              AS open,
    max(yes_bid)                    AS high,
    min(yes_bid)                    AS low,
    last(yes_bid, ts)               AS close,
    sum(volume)                     AS volume,
    last(open_interest, ts)         AS open_interest
FROM market_snapshots
GROUP BY bucket, market_ticker
WITH NO DATA;

-- Continuous aggregate refresh policies
SELECT add_continuous_aggregate_policy('market_ohlc_1min',
    start_offset => INTERVAL '10 minutes',
    end_offset   => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE);

SELECT add_continuous_aggregate_policy('market_ohlc_5min',
    start_offset => INTERVAL '1 hour',
    end_offset   => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE);

SELECT add_continuous_aggregate_policy('market_ohlc_1hour',
    start_offset => INTERVAL '2 days',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);

-- =============================================================================
-- Data Retention Policies
-- =============================================================================

SELECT add_retention_policy('market_snapshots',
    INTERVAL '90 days',
    if_not_exists => TRUE);

SELECT add_retention_policy('portfolio_snapshots',
    INTERVAL '365 days',
    if_not_exists => TRUE);

SELECT add_retention_policy('agent_thoughts',
    INTERVAL '30 days',
    if_not_exists => TRUE);
