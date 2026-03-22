import json
from datetime import datetime

import redis.asyncio as aioredis

CHANNEL_PORTFOLIO_SNAPSHOT = "okane:portfolio:snapshot"
CHANNEL_POSITION_FILL = "okane:position:fill"
CHANNEL_POSITION_CLOSE = "okane:position:close"


async def create_redis(url: str) -> aioredis.Redis:
    return await aioredis.from_url(url, decode_responses=True)


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


async def publish_fill(redis: aioredis.Redis, fill: dict) -> None:
    await redis.publish(CHANNEL_POSITION_FILL, json.dumps(fill, default=_json_default))


async def publish_close(redis: aioredis.Redis, close: dict) -> None:
    await redis.publish(CHANNEL_POSITION_CLOSE, json.dumps(close, default=_json_default))


async def publish_portfolio_snapshot(redis: aioredis.Redis, snapshot: dict) -> None:
    await redis.publish(
        CHANNEL_PORTFOLIO_SNAPSHOT, json.dumps(snapshot, default=_json_default)
    )
