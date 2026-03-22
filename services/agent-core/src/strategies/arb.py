"""
Ladder Monotonicity Arbitrage Strategy.

Within a single expiry event (e.g. KXBTCD-20MAR26), the YES price for each
strike must be monotonically DECREASING as the strike increases:

    P(BTC > $82K) >= P(BTC > $83K) >= P(BTC > $84K) >= ...

This is a logical certainty — if BTC exceeds $83K it also exceeds $82K.
When the market violates this ordering, the lower-strike YES contract is
provably underpriced relative to the higher-strike contract.

This requires zero model assumptions. The only risk is directional
(the asset finishes below both strikes), but the RELATIVE mispricing
is genuinely arb-able and typically corrects within hours.

Only trades in the 4-48h window — enough time for the mispricing to correct
before settlement dynamics distort the ladder.
"""
import re
from datetime import datetime, timezone
from typing import Optional

import structlog

from .base import BaseStrategy, StrategySignal

log = structlog.get_logger()

# Minimum probability violation to act on (filters bid-ask noise)
MIN_VIOLATION = 0.04
# Time window: far enough for correction, not so far that noise dominates
MIN_HOURS_TO_EXPIRY = 8.0
MAX_HOURS_TO_EXPIRY = 48.0
# Need at least this many strikes in the ladder to detect reliable violations
MIN_LADDER_SIZE = 3
# Skip markets near certainty
MIN_YES_PRICE = 0.10
MAX_YES_PRICE = 0.90
# Skip illiquid markets
MAX_SPREAD = 0.06

_THRESHOLD_RE = re.compile(r"-T(\d+(?:\.\d+)?)$", re.IGNORECASE)


def _parse_threshold(ticker: str) -> Optional[float]:
    m = _THRESHOLD_RE.search(ticker)
    return float(m.group(1)) if m else None


class ArbStrategy(BaseStrategy):
    """Ladder arbitrage: buy underpriced YES contracts when strike monotonicity is violated."""

    name = "arb"
    weight = 0.30

    async def analyze(self, ticker, market_data, price_history) -> Optional[StrategySignal]:
        return None  # Only used via analyze_all()

    async def analyze_all(
        self,
        markets: list[dict],
        asset_prices: dict[str, float] | None = None,
        drift: float = 0.0,
    ) -> list[StrategySignal]:
        now = datetime.now(timezone.utc)

        # ── 1. Group markets by event, apply time filter ──────────────────
        events: dict[str, list[dict]] = {}
        for m in markets:
            event = m.get("event_ticker")
            ticker = m.get("market_ticker", "")
            close_time = m.get("close_time")
            threshold = _parse_threshold(ticker)

            if not all([event, close_time, threshold]):
                continue

            if isinstance(close_time, str):
                try:
                    close_time = datetime.fromisoformat(close_time)
                except ValueError:
                    continue
            if close_time.tzinfo is None:
                close_time = close_time.replace(tzinfo=timezone.utc)

            hours_left = (close_time - now).total_seconds() / 3600.0
            if not (MIN_HOURS_TO_EXPIRY <= hours_left <= MAX_HOURS_TO_EXPIRY):
                continue

            yes_bid = m.get("yes_bid")
            yes_ask = m.get("yes_ask")
            if yes_bid is not None and yes_ask is not None:
                yes_mid = (float(yes_bid) + float(yes_ask)) / 2.0
                spread = float(yes_ask) - float(yes_bid)
            elif yes_bid is not None:
                yes_mid = float(yes_bid)
                spread = 0.0
            else:
                last = m.get("last_price")
                if last is None:
                    continue
                yes_mid = float(last)
                spread = 0.0

            if spread > MAX_SPREAD:
                continue

            if event not in events:
                events[event] = []
            events[event].append({
                "ticker": ticker,
                "threshold": threshold,
                "yes_mid": yes_mid,
                "spread": spread,
                "hours_left": hours_left,
            })

        if not events:
            return []

        # ── 2. Scan each event's ladder for monotonicity violations ───────
        signals = []
        for ev_name, ladder in events.items():
            if len(ladder) < MIN_LADDER_SIZE:
                continue

            # Sort ascending by strike price
            ladder.sort(key=lambda x: x["threshold"])

            for i in range(len(ladder) - 1):
                low = ladder[i]   # lower strike → should have HIGHER yes_mid
                high = ladder[i + 1]  # higher strike → should have LOWER yes_mid

                # Violation: higher-strike YES > lower-strike YES
                violation = high["yes_mid"] - low["yes_mid"]

                if violation < MIN_VIOLATION:
                    continue

                market_price = low["yes_mid"]
                if not (MIN_YES_PRICE <= market_price <= MAX_YES_PRICE):
                    continue

                # Buy YES on the lower-strike (logically underpriced)
                confidence = round(min(0.90, 0.65 + violation * 4.0), 4)

                signals.append(StrategySignal(
                    market_ticker=low["ticker"],
                    side="yes",
                    confidence=confidence,
                    raw_score=round(violation, 4),
                    reasoning=(
                        f"Ladder arb [{ev_name}]: "
                        f"P(>{low['threshold']:,.0f}) = {low['yes_mid']:.3f} "
                        f"< P(>{high['threshold']:,.0f}) = {high['yes_mid']:.3f}. "
                        f"Violation = {violation:.3f} — lower strike YES is logically underpriced."
                    ),
                    strategy_name=self.name,
                    metadata={
                        "current_price": market_price,
                        "violation": round(violation, 4),
                        "low_strike": low["threshold"],
                        "high_strike": high["threshold"],
                        "hours_left": round(low["hours_left"], 2),
                    },
                ))

        return signals
