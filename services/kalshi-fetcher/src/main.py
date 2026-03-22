"""
Kalshi Fetcher — main entry point.

Polls the Kalshi REST API and stores market snapshots to TimescaleDB.
Publishes market updates and settlement events to Redis.
"""
import asyncio
import signal
from datetime import datetime, timezone

import structlog
from prometheus_client import Counter, Histogram, Gauge, start_http_server

from .backoff import CircuitBreaker
from .client import KalshiClient
from .config import settings
from .models import MarketSnapshot
from .publisher import create_redis, publish_alert, publish_settlement, publish_snapshot
from .storage import create_pool, insert_snapshots, upsert_market_outcome

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()

# Prometheus metrics
fetch_duration = Histogram("kalshi_fetch_duration_seconds", "Time to fetch a batch of markets")
fetch_errors = Counter("kalshi_api_errors_total", "Kalshi API errors", ["error_type"])
markets_fetched = Gauge("kalshi_markets_active_total", "Number of active markets tracked")
snapshots_stored = Counter("kalshi_snapshots_stored_total", "Total snapshots stored to DB")


def _price(market: dict, *keys) -> float | None:
    """Try multiple field names, return first non-None float."""
    for k in keys:
        v = market.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def market_to_snapshot(market: dict) -> MarketSnapshot:
    return MarketSnapshot(
        ts=datetime.now(timezone.utc),
        market_ticker=market.get("ticker", ""),
        event_ticker=market.get("event_ticker"),
        title=market.get("title"),
        yes_bid=_price(market, "yes_bid_dollars", "yes_bid"),
        yes_ask=_price(market, "yes_ask_dollars", "yes_ask"),
        no_bid=_price(market, "no_bid_dollars", "no_bid"),
        no_ask=_price(market, "no_ask_dollars", "no_ask"),
        last_price=_price(market, "last_price_dollars", "last_price"),
        volume=float(market.get("volume_fp") or market.get("volume") or 0),
        open_interest=float(market.get("open_interest_fp") or market.get("open_interest") or 0),
        liquidity=_price(market, "liquidity_dollars", "liquidity"),
        status=market.get("status"),
        close_time=market.get("close_time"),
        result=market.get("result"),
        raw_json=market,
    )


async def run_fetch_cycle(
    client: KalshiClient,
    pool,
    redis,
    circuit: CircuitBreaker,
    known_settled: set,
    prediction_tickers: list,
) -> None:
    with fetch_duration.time():
        try:
            if settings.series_list:
                markets = await circuit.call(client.get_markets_by_series, settings.series_list)
            elif prediction_tickers:
                markets = await circuit.call(client.get_markets_by_tickers, prediction_tickers)
            else:
                markets = await circuit.call(client.get_markets_page_limited, status="open", max_markets=400)
        except RuntimeError as exc:
            # Circuit is open
            log.error("fetch_skipped_circuit_open", error=str(exc))
            await publish_alert(redis, f"Kalshi fetcher circuit open: {exc}", level="error")
            return
        except Exception as exc:
            fetch_errors.labels(error_type=type(exc).__name__).inc()
            log.error("fetch_error", error=str(exc), exc_info=True)
            return

    # Also check for recently settled markets (one page only — avoid paginating all history)
    try:
        settled_resp = await circuit.call(client.get_markets, limit=200, status="settled")
        settled_markets = settled_resp.get("markets", [])
        for market in settled_markets:
            ticker = market.get("ticker")
            if ticker and ticker not in known_settled:
                known_settled.add(ticker)
                await upsert_market_outcome(pool, market)
                await publish_settlement(redis, market)
    except Exception as exc:
        log.warning("settled_fetch_error", error=str(exc))

    # Only store markets expiring within 30 hours — drop far-dated ones
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    cutoff = now + timedelta(hours=30)
    markets = [
        m for m in markets
        if m.get("close_time") and
        datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")) <= cutoff
    ]

    log.info("fetch_cycle_complete", open_markets=len(markets))
    markets_fetched.set(len(markets))
    snapshots = [market_to_snapshot(m) for m in markets]

    try:
        stored = await insert_snapshots(pool, snapshots)
        snapshots_stored.inc(stored)
    except Exception as exc:
        log.error("db_insert_error", error=str(exc), exc_info=True)
        return

    # Publish to Redis (fire-and-forget; don't block on publish errors)
    for snap in snapshots:
        try:
            await publish_snapshot(redis, snap)
        except Exception as exc:
            log.warning("redis_publish_error", error=str(exc))


async def main() -> None:
    log.info("kalshi_fetcher_starting", interval=settings.fetch_interval_seconds)

    # Start Prometheus metrics server
    start_http_server(9090)

    # Connect to dependencies
    pool = await create_pool(settings.postgres_dsn)
    redis = await create_redis(settings.redis_url)
    client = KalshiClient()
    circuit = CircuitBreaker(failure_threshold=5, reset_timeout=60.0, name="kalshi_api")

    known_settled: set[str] = set()
    prediction_tickers: list[str] = []

    if not settings.series_list:
        # No series configured — deep scan once to find non-parlay tickers
        log.info("ticker_discovery_start")
        try:
            prediction_tickers = await client.discover_prediction_tickers(target=500, max_fetch=15000)
            log.info("ticker_discovery_complete", count=len(prediction_tickers))
        except Exception as exc:
            log.warning("ticker_discovery_failed", error=str(exc))
    else:
        log.info("series_mode", series=settings.series_list)

    shutdown = asyncio.Event()

    def _handle_signal():
        log.info("shutdown_signal_received")
        shutdown.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    log.info("kalshi_fetcher_ready")

    try:
        while not shutdown.is_set():
            await run_fetch_cycle(client, pool, redis, circuit, known_settled, prediction_tickers)
            try:
                await asyncio.wait_for(
                    shutdown.wait(), timeout=settings.fetch_interval_seconds
                )
            except asyncio.TimeoutError:
                pass
    finally:
        await client.close()
        await pool.close()
        await redis.aclose()
        log.info("kalshi_fetcher_stopped")


if __name__ == "__main__":
    asyncio.run(main())
