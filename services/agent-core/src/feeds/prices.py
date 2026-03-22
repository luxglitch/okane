"""
Live asset price feed.
Primary: CoinGecko (free, no key)
Fallback: Kraken public API
Prices are cached in Redis for 60 seconds.
"""
import math

import httpx
import structlog

log = structlog.get_logger()

CACHE_TTL = 60  # seconds

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
KRAKEN_URL = "https://api.kraken.com/0/public/Ticker"

# Maps Kalshi series prefix → (CoinGecko id, Kraken pair)
SERIES_TO_SYMBOL: dict[str, str] = {
    "KXBTCD": "BTCUSDT",
    "KXBTC":  "BTCUSDT",
    "KXETH":  "ETHUSDT",
    "KXETHD": "ETHUSDT",
    "KXDOGE": "DOGEUSDT",
}

_COINGECKO_IDS = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT":  "ethereum",
    "DOGEUSDT": "dogecoin",
}

_KRAKEN_PAIRS = {
    "BTCUSDT": "XBTUSD",
    "ETHUSDT":  "ETHUSD",
    "DOGEUSDT": "XDGUSD",
}


async def fetch_asset_prices(redis, symbols: list[str] | None = None) -> dict[str, float]:
    """
    Returns {symbol: price_usd} for each requested symbol.
    Uses Redis cache; falls back gracefully on errors.
    """
    if symbols is None:
        symbols = list(set(SERIES_TO_SYMBOL.values()))

    prices: dict[str, float] = {}
    uncached: list[str] = []

    for symbol in symbols:
        cached = await redis.get(f"okane:price:{symbol}")
        if cached:
            prices[symbol] = float(cached)
        else:
            uncached.append(symbol)

    if not uncached:
        return prices

    async with httpx.AsyncClient(timeout=5.0) as client:
        # Try CoinGecko for all uncached symbols at once
        cg_ids = [_COINGECKO_IDS[s] for s in uncached if s in _COINGECKO_IDS]
        if cg_ids:
            try:
                resp = await client.get(
                    COINGECKO_URL,
                    params={"ids": ",".join(cg_ids), "vs_currencies": "usd"},
                )
                resp.raise_for_status()
                data = resp.json()
                for symbol in uncached:
                    cg_id = _COINGECKO_IDS.get(symbol)
                    if cg_id and cg_id in data:
                        price = float(data[cg_id]["usd"])
                        prices[symbol] = price
                        await redis.setex(f"okane:price:{symbol}", CACHE_TTL, str(price))
                        log.debug("price_fetched", symbol=symbol, price=price, source="coingecko")
            except Exception as exc:
                log.warning("coingecko_error", error=str(exc))

        # Kraken fallback for anything still missing
        for symbol in uncached:
            if symbol in prices:
                continue
            kraken_pair = _KRAKEN_PAIRS.get(symbol)
            if not kraken_pair:
                continue
            try:
                resp = await client.get(KRAKEN_URL, params={"pair": kraken_pair})
                resp.raise_for_status()
                result = resp.json().get("result", {})
                for v in result.values():
                    price = float(v["c"][0])  # last trade price
                    prices[symbol] = price
                    await redis.setex(f"okane:price:{symbol}", CACHE_TTL, str(price))
                    log.debug("price_fetched", symbol=symbol, price=price, source="kraken")
                    break
            except Exception as exc:
                log.warning("kraken_error", symbol=symbol, error=str(exc))

    return prices


_DRIFT_KEY = "okane:price:btc:5min_ago"
_DRIFT_CAP = 2.0  # annualized, ±


async def estimate_btc_drift(redis, current_price: float) -> float:
    """
    Estimate annualized BTC drift from the 5-minute log return.
    Stores current price in Redis (TTL=6min); returns μ annualized.
    Returns 0.0 if no prior observation yet. Capped at ±2.0.
    """
    prior_raw = await redis.get(_DRIFT_KEY)
    await redis.setex(_DRIFT_KEY, 360, str(current_price))

    if prior_raw is None or float(prior_raw) <= 0:
        return 0.0

    log_ret = math.log(current_price / float(prior_raw))
    # 525_600 minutes per year, measurement interval = 5 min
    annualized = log_ret * (525_600 / 5)
    return max(-_DRIFT_CAP, min(_DRIFT_CAP, annualized))


def series_price(asset_prices: dict[str, float], event_ticker: str) -> float | None:
    """Look up the live price for a given Kalshi event ticker's underlying asset."""
    series = event_ticker.split("-")[0].upper()
    symbol = SERIES_TO_SYMBOL.get(series)
    return asset_prices.get(symbol) if symbol else None
