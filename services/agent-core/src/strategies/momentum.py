"""
Contrarian RSI Strategy.

Uses RSI(14) to detect probability extremes and bet on mean reversion.
Prediction market probabilities are mean-reverting (not trending), so
RSI extremes signal the opposite of traditional momentum:
  - RSI overbought (≥65): probability has risen too fast → bet NO (expect reversion)
  - RSI oversold  (≤35): probability has fallen too fast → bet YES (expect reversion)

Only trades in the 4-48h window where mean reversion reliably operates.
No LLM calls — pure quantitative.
"""
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import structlog

from .base import BaseStrategy, StrategySignal

log = structlog.get_logger()

RSI_PERIOD = 14
RSI_OVERSOLD = 35.0
RSI_OVERBOUGHT = 65.0
MIN_HISTORY = 20
# Only trade when market is genuinely uncertain (not near-certain outcomes)
MIN_YES_PRICE = 0.20
MAX_YES_PRICE = 0.80
MIN_HOURS_TO_EXPIRY = 4.0
MAX_HOURS_TO_EXPIRY = 48.0


def compute_rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0

    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period

    if avg_gain == 0 and avg_loss == 0:
        return 50.0  # Flat market — no momentum
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class MomentumStrategy(BaseStrategy):
    name = "momentum"
    weight = 0.25

    async def analyze(
        self,
        ticker: str,
        market_data: dict,
        price_history: list[dict],
    ) -> Optional[StrategySignal]:
        if len(price_history) < MIN_HISTORY:
            return None

        closes = np.array(
            [float(p["close"]) for p in price_history if p.get("close")], dtype=float
        )
        if len(closes) < MIN_HISTORY:
            return None

        # Only trade in the 4-48h window — near expiry, RSI extremes are just
        # prices converging to settlement, not mean-reversion opportunities.
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

        # Skip flat/synthetic markets — RSI=100 is a degenerate artifact of
        # zero price variance (avg_loss=0), not a real momentum signal.
        if np.std(closes) < 0.005:
            return None

        rsi = compute_rsi(closes, RSI_PERIOD)
        recent_trend = closes[-1] - closes[-5] if len(closes) >= 5 else 0.0

        if RSI_OVERSOLD < rsi < RSI_OVERBOUGHT:
            return None  # No extreme reading

        # Only trade genuinely uncertain markets — skip near-certain outcomes
        yes_price = float(
            market_data.get("yes_bid") or market_data.get("last_price") or 0.5
        )
        yes_price = max(0.01, min(0.99, yes_price))
        if not (MIN_YES_PRICE <= yes_price <= MAX_YES_PRICE):
            return None

        # Prediction market probabilities are MEAN-REVERTING, not trending.
        # RSI extreme signals over-extension — bet on reversion back to fair value.
        # RSI overbought = probability rose too fast → expect reversion down → bet NO
        # RSI oversold   = probability fell too fast → expect reversion up  → bet YES
        if rsi <= RSI_OVERSOLD:
            # YES probability over-extended low → bet YES (expect reversion up)
            side = "yes"
            current_price = yes_price
            confidence = min(0.90, 0.55 + (RSI_OVERSOLD - rsi) / 100)
            reasoning = (
                f"RSI={rsi:.1f} (oversold). YES price over-extended low ({yes_price:.3f}), "
                f"trend: {recent_trend:+.4f}/5bar. Contrarian — expect reversion UP, betting YES."
            )
        else:
            # YES probability over-extended high → bet NO (expect reversion down)
            side = "no"
            current_price = round(1.0 - yes_price, 4)
            confidence = min(0.90, 0.55 + (rsi - RSI_OVERBOUGHT) / 100)
            reasoning = (
                f"RSI={rsi:.1f} (overbought). YES price over-extended high ({yes_price:.3f}), "
                f"trend: {recent_trend:+.4f}/5bar. Contrarian — expect reversion DOWN, betting NO."
            )

        return StrategySignal(
            market_ticker=ticker,
            side=side,
            confidence=round(confidence, 4),
            raw_score=round(rsi, 2),
            reasoning=reasoning,
            strategy_name=self.name,
            metadata={
                "rsi": round(rsi, 2),
                "trend_5bar": round(recent_trend, 4),
                "current_price": current_price,
                "yes_price": yes_price,
            },
        )
