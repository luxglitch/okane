import json
from datetime import datetime, timezone

import asyncpg
import structlog

from .models import MarketSnapshot

log = structlog.get_logger()


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn, min_size=2, max_size=5)


async def insert_snapshots(pool: asyncpg.Pool, snapshots: list[MarketSnapshot]) -> int:
    if not snapshots:
        return 0

    rows = [
        (
            s.ts,
            s.market_ticker,
            s.event_ticker,
            s.title,
            s.yes_bid,
            s.yes_ask,
            s.no_bid,
            s.no_ask,
            s.last_price,
            s.volume,
            s.open_interest,
            s.liquidity,
            s.status,
            s.close_time,
            s.result,
            json.dumps(s.raw_json) if s.raw_json else None,
        )
        for s in snapshots
    ]

    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO market_snapshots (
                ts, market_ticker, event_ticker, title,
                yes_bid, yes_ask, no_bid, no_ask, last_price,
                volume, open_interest, liquidity, status,
                close_time, result, raw_json
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
            """,
            rows,
        )

    log.debug("snapshots_inserted", count=len(rows))
    return len(rows)


async def upsert_market_outcome(pool: asyncpg.Pool, market: dict) -> None:
    ticker = market.get("ticker")
    result = market.get("result")
    if not ticker or not result:
        return

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO market_outcomes (market_ticker, settled_at, result, settlement_price, raw_json)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (market_ticker) DO UPDATE SET
                settled_at = EXCLUDED.settled_at,
                result = EXCLUDED.result,
                settlement_price = EXCLUDED.settlement_price,
                raw_json = EXCLUDED.raw_json
            """,
            ticker,
            datetime.now(timezone.utc),
            result,
            market.get("last_price"),
            json.dumps(market),
        )
