"""
Statistical Arbitrage Strategy.

Detects mean-reversion opportunities using z-score analysis.
When price deviates significantly from its rolling mean, bet on reversion.
Only trades in the 4-48h to expiry window where mean-reversion reliably works.
No LLM calls — pure quantitative.
"""
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import structlog

from .base import BaseStrategy, StrategySignal

log = structlog.get_logger()

Z_SCORE_THRESHOLD = 1.5
MIN_HISTORY_POINTS = 20
MIN_YES_PRICE = 0.10
MAX_YES_PRICE = 0.90
# Max price to PAY per contract — always bet the cheap side.
# Paying >45c means worst-case loss exceeds best-case gain. Skip it.
MAX_BET_PRICE = 0.45
# Only trade in the sweet spot: far enough out for mean reversion to work,
# close enough that the signal is still relevant.
MIN_HOURS_TO_EXPIRY = 8.0
MAX_HOURS_TO_EXPIRY = 48.0


class StatArbStrategy(BaseStrategy):
    name = "stat_arb"
    weight = 0.25

    async def analyze(
        self,
        ticker: str,
        market_data: dict,
        price_history: list[dict],
    ) -> Optional[StrategySignal]:
        if len(price_history) < MIN_HISTORY_POINTS:
            return None

        closes = np.array([float(p["close"]) for p in price_history if p.get("close")], dtype=float)
        if len(closes) < MIN_HISTORY_POINTS:
            return None

        # Only trade in the 4-48h window — mean reversion doesn't work near expiry
        # (prices converge to 0/1 at settlement) or very far out (too noisy).
        close_time = market_data.get("close_time")
        if close_time is not None:
            now = datetime.now(timezone.utc)
            if isinstance(close_time, str):
                close_time = datetime.fromisoformat(close_time)
            if close_time.tzinfo is None:
                close_time = close_time.replace(tzinfo=timezone.utc)
            hours_left = (close_time - now).total_seconds() / 3600.0
            if not (MIN_HOURS_TO_EXPIRY <= hours_left <= MAX_HOURS_TO_EXPIRY):
                return None

        current_price = market_data.get("yes_bid") or market_data.get("last_price")
        if current_price is None:
            return None

        current_price = float(current_price)
        # Only trade genuinely uncertain markets
        if not (MIN_YES_PRICE <= current_price <= MAX_YES_PRICE):
            return None
        mean = np.mean(closes)
        std = np.std(closes)

        if std < 0.005:  # Too little volatility — no signal
            return None

        z = (current_price - mean) / std

        if abs(z) < Z_SCORE_THRESHOLD:
            return None

        # Price is far above mean → expect reversion down → bet NO
        # Price is far below mean → expect reversion up → bet YES
        side = "no" if z > 0 else "yes"
        bet_price = round(
            (1.0 - current_price) if side == "no" else current_price, 4
        )

        # Only bet the cheap side. Paying >45c means max loss > max gain.
        # e.g. YES at 0.70: win +$0.30, lose -$0.70 — terrible risk/reward.
        # e.g. YES at 0.25: win +$0.75, lose -$0.25 — excellent.
        if bet_price > MAX_BET_PRICE:
            return None

        confidence = min(0.95, 0.50 + (abs(z) - Z_SCORE_THRESHOLD) * 0.10)

        return StrategySignal(
            market_ticker=ticker,
            side=side,
            confidence=round(confidence, 4),
            raw_score=round(abs(z), 4),
            reasoning=(
                f"Z-score={z:.2f} (mean={mean:.3f}, std={std:.3f}, current={current_price:.3f}). "
                f"Price is {abs(z):.1f}σ {'above' if z > 0 else 'below'} mean — "
                f"betting on mean reversion toward {side.upper()}."
            ),
            strategy_name=self.name,
            metadata={
                "z_score": round(z, 4),
                "mean": round(mean, 4),
                "std": round(std, 4),
                "current_price": bet_price,
            },
        )
