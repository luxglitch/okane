"""
Agent Core — main decision loop.

Observe → Manage → Scan → Rank → Enhance → Risk Check → Execute → Record → Learn
"""
import asyncio
import json
import signal
import time
from datetime import datetime, timezone

import redis.asyncio as aioredis
import structlog
from prometheus_client import Counter, Gauge, Histogram, start_http_server

from .broker_client import BrokerClient
from .config import settings
from .feeds.prices import fetch_asset_prices, estimate_btc_drift
from .feeds.settlement import settle_expired_positions
from .database import (
    create_pool,
    fetch_pending_settlements,
    fetch_price_history,
    fetch_recent_markets,
    save_signal,
    save_thought,
)
from .learning.chroma_client import ChromaStore
from .learning.post_mortem import PostMortemAnalyzer
from .learning.weight_tuner import load_active_weights, run_weight_optimization
from .llm.client import LLMClient
from .llm.signal_enhancer import SignalEnhancer
from .risk.kelly import compute_contracts, kelly_fraction
from .risk.limits import RiskChecker
from .strategies.arb import ArbStrategy
from .strategies.momentum import MomentumStrategy
from .strategies.pattern import PatternStrategy
from .strategies.sentiment import SentimentStrategy
from .strategies.stat_arb import StatArbStrategy

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()

# Prometheus metrics
signals_generated = Counter("agent_signals_generated_total", "Signals generated", ["strategy"])
orders_placed = Counter("agent_orders_placed_total", "Orders placed")
orders_skipped = Counter("agent_orders_skipped_total", "Orders skipped", ["reason"])
portfolio_value = Gauge("portfolio_value_dollars", "Current portfolio value")
cycle_duration = Histogram("agent_cycle_duration_seconds", "Agent cycle time")

REDIS_CHANNEL_SIGNAL = "okane:agent:signal"
REDIS_CHANNEL_THOUGHT = "okane:agent:thought"
REDIS_CHANNEL_WEIGHTS = "okane:agent:weights"
BTC_MACRO_STOP_THRESHOLD = 0.008  # 0.8% move triggers portfolio-wide close
REDIS_BTC_LAST_CYCLE_KEY = "okane:btc:last_cycle"


async def publish_thought(redis: aioredis.Redis, thought_type: str, content: str, ticker: str = None):
    payload = {
        "type": thought_type,
        "content": content,
        "ticker": ticker,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await redis.publish(REDIS_CHANNEL_THOUGHT, json.dumps(payload))


async def agent_loop(
    pool,
    redis: aioredis.Redis,
    broker: BrokerClient,
    chroma: ChromaStore,
    llm: LLMClient,
    risk: RiskChecker,
    enhancer: SignalEnhancer,
    post_mortem: PostMortemAnalyzer,
):
    # Load strategy weights
    weights = await load_active_weights(pool)
    arb = ArbStrategy()
    strategies = [
        SentimentStrategy(),
        StatArbStrategy(),
        PatternStrategy(chroma_store=chroma),
        # MomentumStrategy disabled: 8.8% win rate, loses ~$104/trade regardless of direction
    ]
    for s in [arb] + strategies:
        s.weight = weights.get(s.name, 0.25)

    cycle_count = 0
    last_weight_update = time.monotonic()
    WEIGHT_UPDATE_INTERVAL = 7 * 24 * 3600  # weekly

    while True:
        cycle_start = time.monotonic()
        cycle_count += 1
        log.info("agent_cycle_start", cycle=cycle_count)
        await publish_thought(redis, "observation", f"Starting cycle #{cycle_count}")

        try:
            # ── 1. OBSERVE ────────────────────────────────────────────────
            portfolio = await broker.get_portfolio()
            open_positions = await broker.get_positions(status="open")
            markets = await fetch_recent_markets(pool)
            asset_prices = await fetch_asset_prices(redis)

            # BTC macro stop: if BTC moved >0.8% since last cycle, close all
            btc_price_now = asset_prices.get("BTCUSDT")
            btc_drift = 0.0
            if btc_price_now:
                btc_last_raw = await redis.get(REDIS_BTC_LAST_CYCLE_KEY)
                if btc_last_raw is not None:
                    btc_last = float(btc_last_raw)
                    if btc_last > 0:
                        btc_move = abs(btc_price_now - btc_last) / btc_last
                        if btc_move > BTC_MACRO_STOP_THRESHOLD:
                            log.warning("btc_macro_stop_triggered",
                                btc_now=btc_price_now, btc_last=btc_last,
                                move_pct=round(btc_move * 100, 3))
                            await publish_thought(redis, "decision",
                                f"BTC macro stop: {btc_move:.1%} move "
                                f"(${btc_last:,.0f}→${btc_price_now:,.0f}). Closing all.")
                            for pos in open_positions:
                                try:
                                    ep = float(pos.get("yes_bid") or pos.get("last_price") or 0.5)
                                    await broker.close_position(
                                        pos["id"], ep, close_reason="btc_macro_stop"
                                    )
                                except Exception as exc:
                                    log.warning("macro_stop_close_error",
                                        ticker=pos.get("market_ticker"), error=str(exc))
                            open_positions = await broker.get_positions(status="open")
                try:
                    btc_drift = await estimate_btc_drift(redis, btc_price_now)
                except Exception as exc:
                    log.warning("drift_estimate_error", error=str(exc))
                await redis.set(REDIS_BTC_LAST_CYCLE_KEY, str(btc_price_now))

            portfolio_value.set(portfolio.get("total_value", 0))
            await save_thought(pool, "observation",
                f"Portfolio: ${portfolio.get('total_value', 0):.2f} | "
                f"Open positions: {len(open_positions)} | Active markets: {len(markets)}")

            if not markets:
                log.info("no_markets_available")
                await asyncio.sleep(settings.agent_cycle_seconds)
                continue

            # ── 2. MANAGE EXISTING POSITIONS ─────────────────────────────
            for pos in open_positions:
                ticker = pos.get("market_ticker")
                market = next((m for m in markets if m["market_ticker"] == ticker), None)
                if not market:
                    continue

                yes_bid = market.get("yes_bid")
                current_price = float(
                    yes_bid if yes_bid is not None else (market.get("last_price") or 0.5)
                )
                entry = float(pos.get("entry_price", 0.5))
                side = pos.get("side")
                effective_price = current_price if side == "yes" else round(1.0 - current_price, 4)
                effective_entry = entry

                close_reason = None
                close_price = effective_price

                # Profit target: close when up 40%+ on the position
                if effective_entry > 0:
                    gain = (effective_price - effective_entry) / effective_entry
                    if gain >= 0.40:
                        close_reason = "profit_target"

                # Stop-loss: 50% loss on position
                if not close_reason:
                    if side == "yes" and current_price < entry * 0.5:
                        close_reason = "stop_loss"
                        close_price = current_price
                    elif side == "no" and current_price > entry + (1 - entry) * 0.5:
                        close_reason = "stop_loss"
                        close_price = round(1.0 - current_price, 4)

                if close_reason:
                    try:
                        await broker.close_position(pos["id"], close_price, close_reason=close_reason)
                        await publish_thought(redis, "decision",
                            f"{close_reason} on {ticker} {side.upper()} @ {close_price:.3f}", ticker=ticker)
                    except Exception as exc:
                        log.warning("position_close_error", ticker=ticker, reason=close_reason, error=str(exc))

            # Settle any expired positions at full $1.00/$0.00 settlement price
            try:
                settled = await settle_expired_positions(pool, broker)
                for s in settled:
                    await publish_thought(redis, "decision",
                        f"✅ Settled {s['market_ticker']} → {s['result'].upper()} ({'WIN' if s['won'] else 'LOSS'})",
                        ticker=s["market_ticker"])
            except Exception as exc:
                log.warning("settlement_error", error=str(exc))

            # ── 3. SCAN FOR SIGNALS ───────────────────────────────────────
            all_signals = []
            for market in markets:
                ticker = market["market_ticker"]
                try:
                    history = await fetch_price_history(pool, ticker, limit=50)
                    for strategy in strategies:
                        sig = await strategy.analyze(ticker, market, history)
                        if sig and sig.confidence >= settings.min_signal_confidence:
                            all_signals.append(sig)
                            signals_generated.labels(strategy=strategy.name).inc()
                except Exception as exc:
                    log.warning("strategy_error", ticker=ticker, error=str(exc))

            # Arb strategy scans all markets as a group (calibration arb)
            try:
                arb_sigs = await arb.analyze_all(markets, asset_prices=asset_prices, drift=btc_drift)
                for sig in arb_sigs:
                    if sig.confidence >= settings.min_signal_confidence:
                        all_signals.append(sig)
                        signals_generated.labels(strategy=arb.name).inc()
            except Exception as exc:
                log.warning("arb_strategy_error", error=str(exc))

            await save_thought(pool, "observation",
                f"Scan complete: {len(all_signals)} signals across {len(markets)} markets")
            await publish_thought(redis, "observation",
                f"🔍 Scanning {len(markets)} markets — found {len(all_signals)} signals")

            # ── 4. RANK SIGNALS ───────────────────────────────────────────
            # Weighted score = confidence * strategy_weight
            for sig in all_signals:
                strat = next((s for s in strategies if s.name == sig.strategy_name), None)
                sig._weighted_score = sig.confidence * (strat.weight if strat else 0.25)

            # Sort by weighted score, deduplicate by event_ticker+side
            # (KXBTCD markets share the same event; only take the best signal per event)
            market_map = {m["market_ticker"]: m for m in markets}
            all_signals.sort(key=lambda s: s._weighted_score, reverse=True)
            seen = set()
            ranked = []
            for sig in all_signals:
                m = market_map.get(sig.market_ticker, {})
                event = m.get("event_ticker") or sig.market_ticker
                key = (event, sig.side)
                if key not in seen:
                    seen.add(key)
                    ranked.append(sig)

            # ── 5. LLM ENHANCEMENT (top 3 only) ──────────────────────────
            enhanced_signals = []
            for sig in ranked[:3]:
                market = next(
                    (m for m in markets if m["market_ticker"] == sig.market_ticker),
                    {"title": sig.market_ticker},
                )
                await publish_thought(redis, "hypothesis",
                    f"📊 Analyzing {sig.market_ticker} {sig.side.upper()} "
                    f"[{sig.strategy_name}] confidence={sig.confidence:.0%}", ticker=sig.market_ticker)
                try:
                    enhanced = await enhancer.enhance(sig, market)
                    enhanced_signals.append(enhanced)
                except Exception as exc:
                    log.warning("enhance_error", ticker=sig.market_ticker, error=str(exc))
                    enhanced_signals.append(sig)

            # Add remaining non-enhanced signals
            enhanced_signals.extend(ranked[3:10])  # Next 7 un-enhanced

            # ── 6. RISK CHECK + SIZE ──────────────────────────────────────
            orders_to_place = []
            for sig in enhanced_signals:
                if sig.confidence < settings.min_signal_confidence:
                    orders_skipped.labels(reason="low_confidence").inc()
                    continue

                price = sig.metadata.get("current_price") or 0.5
                kf = kelly_fraction(sig.confidence, price)
                total_value = portfolio.get("total_value", settings.starting_balance)
                n_contracts = compute_contracts(total_value, kf, price)

                if n_contracts < 1:
                    orders_skipped.labels(reason="zero_contracts").inc()
                    continue

                approved, reason = risk.check_signal(
                    ticker=sig.market_ticker,
                    side=sig.side,
                    suggested_contracts=n_contracts,
                    suggested_price=price,
                    portfolio=portfolio,
                    open_positions=open_positions,
                )

                if not approved:
                    await publish_thought(redis, "decision",
                        f"❌ Skipped {sig.market_ticker}: {reason}", ticker=sig.market_ticker)
                    await save_thought(pool, "decision",
                        f"Signal skipped: {reason}", market_ticker=sig.market_ticker)
                    orders_skipped.labels(reason="risk_check").inc()
                    continue

                orders_to_place.append((sig, kf, n_contracts, price))

            # ── 7. EXECUTE ORDERS ─────────────────────────────────────────
            for sig, kf, n_contracts, price in orders_to_place:
                try:
                    # Save signal first to get its ID
                    signal_id = await save_signal(
                        pool, sig,
                        kelly_fraction=kf,
                        suggested_contracts=n_contracts,
                        suggested_price=price,
                        executed=False,
                    )

                    fill = await broker.place_order(
                        market_ticker=sig.market_ticker,
                        side=sig.side,
                        contracts=n_contracts,
                        limit_price=price,
                        signal_id=str(signal_id),
                    )

                    # Update signal as executed
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE trade_signals SET executed=TRUE, execution_id=$1 WHERE id=$2",
                            fill.get("position_id"),
                            signal_id,
                        )

                    orders_placed.inc()
                    await publish_thought(redis, "decision",
                        f"✅ Trade entered: {sig.market_ticker} {sig.side.upper()} "
                        f"x{n_contracts} @ {fill.get('fill_price', price):.3f} "
                        f"[{sig.strategy_name}]", ticker=sig.market_ticker)
                    await redis.publish(REDIS_CHANNEL_SIGNAL, json.dumps({
                        "market_ticker": sig.market_ticker,
                        "strategy": sig.strategy_name,
                        "confidence": sig.confidence,
                        "side": sig.side,
                        "reasoning_preview": sig.reasoning[:200],
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }))

                except Exception as exc:
                    log.error("order_error", ticker=sig.market_ticker, error=str(exc))
                    await save_thought(pool, "error",
                        f"Order failed: {exc}", market_ticker=sig.market_ticker)

            # ── 8. SELF-LEARNING: Process settlements ─────────────────────
            pending = await fetch_pending_settlements(pool)
            for item in pending:
                try:
                    await post_mortem.process_settlement(
                        item["market_ticker"], item["result"]
                    )
                    await publish_thought(redis, "reflection",
                        f"📚 Post-mortem: {item['market_ticker']} resolved {item['result']}",
                        ticker=item["market_ticker"])
                except Exception as exc:
                    log.warning("post_mortem_error", ticker=item["market_ticker"], error=str(exc))

            # ── 9. WEIGHT TUNING (every 10 closed trades or weekly) ───────
            closed_count = await pool.fetchval("SELECT COUNT(*) FROM positions WHERE status='closed'")
            time_due = time.monotonic() - last_weight_update > WEIGHT_UPDATE_INTERVAL
            trades_due = closed_count and closed_count >= 10 and closed_count % 10 == 0
            if time_due or trades_due:
                try:
                    new_weights = await run_weight_optimization(pool)
                    if new_weights:
                        for s in [arb] + strategies:
                            s.weight = new_weights.get(s.name, 0.25)
                        last_weight_update = time.monotonic()
                        await redis.publish(REDIS_CHANNEL_WEIGHTS, json.dumps(new_weights))
                        await publish_thought(redis, "reflection",
                            f"📚 Strategy weights updated: {new_weights}")
                except Exception as exc:
                    log.warning("weight_tuner_error", error=str(exc))

        except Exception as exc:
            log.error("agent_cycle_error", cycle=cycle_count, error=str(exc), exc_info=True)
            await save_thought(pool, "error", f"Cycle #{cycle_count} error: {exc}")

        finally:
            elapsed = time.monotonic() - cycle_start
            cycle_duration.observe(elapsed)
            log.info("agent_cycle_end", cycle=cycle_count, duration_s=round(elapsed, 2))

        # Wait for next cycle
        sleep_time = max(0, settings.agent_cycle_seconds - (time.monotonic() - cycle_start))
        await asyncio.sleep(sleep_time)


async def main() -> None:
    log.info("agent_core_starting")
    start_http_server(9090)

    pool = await create_pool(settings.postgres_dsn)
    redis = await aioredis.from_url(settings.redis_url, decode_responses=True)
    broker = BrokerClient()
    chroma = ChromaStore(host=settings.chroma_host, port=settings.chroma_port)
    llm = LLMClient(redis=redis, pool=pool)
    enhancer = SignalEnhancer(llm=llm, chroma_store=chroma)
    risk = RiskChecker()
    post_mortem = PostMortemAnalyzer(pool=pool, llm=llm, chroma=chroma)

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    log.info("agent_core_ready")

    try:
        agent_task = asyncio.create_task(
            agent_loop(pool, redis, broker, chroma, llm, risk, enhancer, post_mortem)
        )
        await shutdown.wait()
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass
    finally:
        await broker.close()
        await pool.close()
        await redis.aclose()
        log.info("agent_core_stopped")


if __name__ == "__main__":
    asyncio.run(main())
