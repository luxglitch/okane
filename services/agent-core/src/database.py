"""
Database helpers for agent-core.
"""
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
import structlog

log = structlog.get_logger()


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn, min_size=3, max_size=10)


async def fetch_recent_markets(pool: asyncpg.Pool, minutes: int = 5) -> list[dict]:
    """Fetch the most recent snapshot for each market from the last N minutes."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (market_ticker)
                market_ticker, event_ticker, title,
                yes_bid, yes_ask, no_bid, no_ask, last_price,
                volume, open_interest, status, close_time, result, ts
            FROM market_snapshots
            WHERE ts >= NOW() - INTERVAL '5 minutes'
              AND status NOT IN ('settled', 'finalized')
              AND (close_time IS NULL OR (close_time > NOW() AND close_time <= NOW() + INTERVAL '7 days'))
            ORDER BY market_ticker, ts DESC
            LIMIT 500
            """
        )
    return [dict(r) for r in rows]


async def fetch_price_history(
    pool: asyncpg.Pool,
    ticker: str,
    limit: int = 50,
) -> list[dict]:
    """Fetch price history. Uses 5-min OHLC when available, falls back to raw snapshots."""
    # Try OHLC table first (may not exist yet); use a separate connection so
    # a missing-table error doesn't poison the connection used by the fallback.
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT bucket AS ts, open, high, low, close, volume
                FROM market_ohlc_5min
                WHERE market_ticker = $1
                ORDER BY bucket DESC
                LIMIT $2
                """,
                ticker,
                limit,
            )
        if len(rows) >= 10:
            return [dict(r) for r in reversed(rows)]
    except Exception:
        pass  # Table doesn't exist yet — fall through to raw snapshots

    # Not enough OHLC bars yet — use raw snapshots as synthetic OHLC
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                ts,
                COALESCE(yes_bid, last_price, 0.5) AS open,
                COALESCE(yes_bid, last_price, 0.5) AS high,
                COALESCE(yes_bid, last_price, 0.5) AS low,
                COALESCE(yes_bid, last_price, 0.5) AS close,
                volume
            FROM market_snapshots
            WHERE market_ticker = $1
              AND (yes_bid IS NOT NULL OR last_price IS NOT NULL)
            ORDER BY ts DESC
            LIMIT $2
            """,
            ticker,
            limit,
        )
    return [dict(r) for r in reversed(rows)]


async def save_signal(
    pool: asyncpg.Pool,
    signal,
    kelly_fraction: float,
    suggested_contracts: int,
    suggested_price: float,
    executed: bool = False,
    execution_id: Optional[UUID] = None,
) -> UUID:
    async with pool.acquire() as conn:
        signal_id = await conn.fetchval(
            """
            INSERT INTO trade_signals (
                ts, market_ticker, strategy_name, side, confidence,
                raw_score, kelly_fraction, suggested_contracts, suggested_price,
                reasoning, llm_enhanced, executed, execution_id
            ) VALUES (NOW(),$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            RETURNING id
            """,
            signal.market_ticker,
            signal.strategy_name,
            signal.side,
            signal.confidence,
            signal.raw_score,
            kelly_fraction,
            suggested_contracts,
            suggested_price,
            signal.reasoning[:2000] if signal.reasoning else "",
            signal.metadata.get("llm_enhanced", False),
            executed,
            execution_id,
        )
    return signal_id


async def save_thought(
    pool: asyncpg.Pool,
    thought_type: str,
    content: str,
    market_ticker: Optional[str] = None,
    metadata: Optional[dict] = None,
    duration_ms: Optional[int] = None,
) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_thoughts (thought_type, market_ticker, content, metadata, duration_ms)
                VALUES ($1,$2,$3,$4,$5)
                """,
                thought_type,
                market_ticker,
                content[:4000],
                json.dumps(metadata) if metadata else None,
                duration_ms,
            )
    except Exception as exc:
        log.warning("save_thought_error", error=str(exc))


async def fetch_pending_settlements(pool: asyncpg.Pool) -> list[dict]:
    """Find markets that have settled but whose positions haven't had post-mortems generated."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT p.market_ticker, mo.result
            FROM positions p
            JOIN market_outcomes mo ON mo.market_ticker = p.market_ticker
            LEFT JOIN post_mortems pm ON pm.position_id = p.id
            WHERE p.status = 'closed'
              AND pm.id IS NULL
              AND mo.result IS NOT NULL
            LIMIT 20
            """
        )
    return [dict(r) for r in rows]
