"""
Pattern Matching Strategy.

Encodes current price pattern as a normalized vector, queries ChromaDB
for historically similar patterns, and uses their outcomes to predict.
"""
from typing import Optional

import numpy as np
import structlog

from .base import BaseStrategy, StrategySignal

log = structlog.get_logger()

PATTERN_WINDOW = 20
MIN_SIMILAR_PATTERNS = 2
MIN_WIN_RATE = 0.60


class PatternStrategy(BaseStrategy):
    name = "pattern"
    weight = 0.25

    def __init__(self, chroma_store=None):
        self.chroma_store = chroma_store

    async def analyze(
        self,
        ticker: str,
        market_data: dict,
        price_history: list[dict],
    ) -> Optional[StrategySignal]:
        if not self.chroma_store:
            return None
        if len(price_history) < PATTERN_WINDOW:
            return None

        closes = [float(p["close"]) for p in price_history[-PATTERN_WINDOW:] if p.get("close")]
        if len(closes) < PATTERN_WINDOW:
            return None

        # Normalize: z-score the window
        arr = np.array(closes, dtype=float)
        std = np.std(arr)
        if std < 0.001:
            return None
        normalized = ((arr - np.mean(arr)) / std).tolist()

        try:
            similar = await self.chroma_store.query_similar_patterns(
                normalized, n_results=10
            )
        except Exception as exc:
            log.warning("pattern_chroma_query_error", error=str(exc))
            return None

        if len(similar) < MIN_SIMILAR_PATTERNS:
            return None

        yes_wins = sum(1 for s in similar if s.get("outcome") == "yes")
        no_wins = sum(1 for s in similar if s.get("outcome") == "no")
        total = yes_wins + no_wins

        if total == 0:
            return None

        yes_rate = yes_wins / total
        no_rate = no_wins / total

        if yes_rate >= MIN_WIN_RATE:
            side = "yes"
            confidence = min(0.90, 0.50 + yes_rate * 0.40)
        elif no_rate >= MIN_WIN_RATE:
            side = "no"
            confidence = min(0.90, 0.50 + no_rate * 0.40)
        else:
            return None

        return StrategySignal(
            market_ticker=ticker,
            side=side,
            confidence=round(confidence, 4),
            raw_score=round(max(yes_rate, no_rate), 4),
            reasoning=(
                f"Found {len(similar)} similar historical patterns. "
                f"YES outcome: {yes_wins}/{total} ({yes_rate:.0%}), "
                f"NO outcome: {no_wins}/{total} ({no_rate:.0%}). "
                f"Historical base rate suggests {side.upper()}."
            ),
            strategy_name=self.name,
            metadata={"similar_count": len(similar), "yes_rate": yes_rate, "no_rate": no_rate},
        )
