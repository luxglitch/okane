import json

import redis.asyncio as aioredis
import structlog

from .models import MarketSnapshot

log = structlog.get_logger()

CHANNEL_MARKET_UPDATE = "okane:market:update"
CHANNEL_MARKET_SETTLEMENT = "okane:market:settlement"
CHANNEL_SYSTEM_ALERT = "okane:system:alert"


async def create_redis(url: str) -> aioredis.Redis:
    return await aioredis.from_url(url, decode_responses=True)


async def publish_snapshot(redis: aioredis.Redis, snapshot: MarketSnapshot) -> None:
    payload = {
        "ticker": snapshot.market_ticker,
        "yes_bid": snapshot.yes_bid,
        "yes_ask": snapshot.yes_ask,
        "no_bid": snapshot.no_bid,
        "no_ask": snapshot.no_ask,
        "last_price": snapshot.last_price,
        "volume": snapshot.volume,
        "open_interest": snapshot.open_interest,
        "status": snapshot.status,
        "ts": snapshot.ts.isoformat(),
    }
    await redis.publish(CHANNEL_MARKET_UPDATE, json.dumps(payload))


async def publish_settlement(redis: aioredis.Redis, market: dict) -> None:
    payload = {
        "ticker": market.get("ticker"),
        "result": market.get("result"),
        "settlement_price": market.get("last_price"),
        "ts": market.get("close_time"),
    }
    await redis.publish(CHANNEL_MARKET_SETTLEMENT, json.dumps(payload))
    log.info("settlement_published", ticker=market.get("ticker"), result=market.get("result"))


async def publish_alert(redis: aioredis.Redis, message: str, level: str = "warning") -> None:
    payload = {"level": level, "message": message}
    await redis.publish(CHANNEL_SYSTEM_ALERT, json.dumps(payload))
