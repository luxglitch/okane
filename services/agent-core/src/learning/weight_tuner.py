"""
Optuna-based strategy weight optimization.

Runs periodically (e.g., weekly) to find optimal strategy weights
by backtesting against historical signals and outcomes.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
import optuna
import structlog

log = structlog.get_logger()

# Suppress Optuna's verbose output
optuna.logging.set_verbosity(optuna.logging.WARNING)

STRATEGY_NAMES = ["sentiment", "stat_arb", "momentum", "pattern", "arb"]


def _backtest_sync(weights: dict, records: list[dict]) -> float:
    """
    Synchronous backtest: given weights and historical signal records,
    compute what the portfolio PnL would have been.
    """
    if not records:
        return 0.0

    total_pnl = 0.0
    for rec in records:
        strategy = rec.get("strategy_name")
        weight = weights.get(strategy, 0.25)
        executed = rec.get("executed", False)
        pnl = float(rec.get("pnl") or 0)

        if executed:
            # Weight-adjusted PnL contribution
            total_pnl += pnl * weight

    return total_pnl


async def _fetch_signal_history(pool: asyncpg.Pool, lookback_days: int = 30) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ts.strategy_name, ts.confidence, ts.executed,
                   ts.execution_id, p.pnl
            FROM trade_signals ts
            LEFT JOIN positions p ON p.id = ts.execution_id
            WHERE ts.ts >= $1
            """,
            cutoff,
        )
    return [dict(r) for r in rows]


async def run_weight_optimization(pool: asyncpg.Pool, n_trials: int = 50) -> Optional[dict]:
    """
    Run Optuna optimization and save best weights to DB.
    Returns the best weights dict or None if no data.
    """
    records = await _fetch_signal_history(pool)
    if len(records) < 10:
        log.info("weight_tuner_insufficient_data", record_count=len(records))
        return None

    log.info("weight_tuner_starting", records=len(records), trials=n_trials)

    def objective(trial):
        raw_weights = {
            name: trial.suggest_float(name, 0.05, 0.60)
            for name in STRATEGY_NAMES
        }
        total = sum(raw_weights.values())
        weights = {k: v / total for k, v in raw_weights.items()}
        return _backtest_sync(weights, records)

    study = optuna.create_study(direction="maximize")
    # Optuna is synchronous; run in executor to avoid blocking event loop
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: study.optimize(objective, n_trials=n_trials, show_progress_bar=False),
    )

    best = study.best_params
    total = sum(best.values())
    best_weights = {k: round(v / total, 4) for k, v in best.items()}
    best_value = study.best_value

    log.info("weight_tuner_complete", best_weights=best_weights, pnl=best_value)

    # Save to DB
    async with pool.acquire() as conn:
        # Deactivate old weights
        await conn.execute(
            "UPDATE agent_weights SET is_active=FALSE WHERE is_active=TRUE"
        )
        for strategy_name, weight in best_weights.items():
            await conn.execute(
                """
                INSERT INTO agent_weights (strategy_name, weight, optuna_value, is_active)
                VALUES ($1, $2, $3, TRUE)
                """,
                strategy_name,
                weight,
                best_value,
            )

    return best_weights


async def load_active_weights(pool: asyncpg.Pool) -> dict:
    """Load the currently active strategy weights from DB."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT strategy_name, weight FROM agent_weights WHERE is_active=TRUE ORDER BY updated_at DESC"
        )

    weights = {}
    seen = set()
    for row in rows:
        name = row["strategy_name"]
        if name not in seen:
            weights[name] = float(row["weight"])
            seen.add(name)

    # Fill in defaults for any missing strategies
    for name in STRATEGY_NAMES:
        if name not in weights:
            weights[name] = 0.25

    return weights
