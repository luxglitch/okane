"""
Sentiment Strategy.

Analyzes market title/description for bullish/bearish signals.
Optionally enhanced with LLM analysis.
"""
from typing import Optional
import re

import structlog

from .base import BaseStrategy, StrategySignal

log = structlog.get_logger()

# Keywords that suggest YES (the event WILL happen)
BULLISH_KEYWORDS = [
    "exceed", "above", "higher", "increase", "rise", "gain", "growth",
    "record", "beat", "surpass", "outperform", "up", "bullish", "positive",
    "win", "approve", "pass", "confirm", "succeed",
]

# Keywords that suggest NO (the event WON'T happen)
BEARISH_KEYWORDS = [
    "below", "under", "lower", "decrease", "fall", "drop", "decline",
    "miss", "fail", "reject", "deny", "lose", "bearish", "negative",
    "unlikely", "unlikely",
]

# Multiplier keywords
STRONG_MULTIPLIER_WORDS = ["significantly", "dramatically", "sharply", "strongly"]


class SentimentStrategy(BaseStrategy):
    name = "sentiment"
    weight = 0.25

    async def analyze(
        self,
        ticker: str,
        market_data: dict,
        price_history: list[dict],
    ) -> Optional[StrategySignal]:
        title = (market_data.get("title") or "").lower()
        if not title:
            return None

        current_price = market_data.get("yes_bid") or market_data.get("last_price") or 0.5
        current_price = float(current_price)

        bullish_score = self._score_keywords(title, BULLISH_KEYWORDS)
        bearish_score = self._score_keywords(title, BEARISH_KEYWORDS)

        # Apply strong multiplier
        for word in STRONG_MULTIPLIER_WORDS:
            if word in title:
                bullish_score *= 1.3
                bearish_score *= 1.3
                break

        net_score = bullish_score - bearish_score

        if abs(net_score) < 1.0:
            return None  # Too neutral — no signal

        # Compare sentiment bias against current market price
        # If market already prices in the sentiment, signal is weak
        if net_score > 0:
            side = "yes"
            # Strong YES signal is most valuable when market underprices YES (price < 0.5)
            price_edge = max(0, 0.5 - current_price)
            confidence = min(0.85, 0.55 + net_score * 0.05 + price_edge * 0.3)
        else:
            side = "no"
            # Strong NO signal is most valuable when market overprices YES (price > 0.5)
            price_edge = max(0, current_price - 0.5)
            confidence = min(0.85, 0.55 + abs(net_score) * 0.05 + price_edge * 0.3)

        return StrategySignal(
            market_ticker=ticker,
            side=side,
            confidence=round(confidence, 4),
            raw_score=round(net_score, 4),
            reasoning=(
                f"Sentiment analysis on '{title[:80]}...'. "
                f"Bullish score: {bullish_score:.1f}, bearish: {bearish_score:.1f}. "
                f"Net: {net_score:+.1f} → {side.upper()} at current price {current_price:.2f}."
            ),
            strategy_name=self.name,
            metadata={
                "bullish_score": round(bullish_score, 2),
                "bearish_score": round(bearish_score, 2),
                "current_price": current_price,
            },
        )

    def _score_keywords(self, text: str, keywords: list[str]) -> float:
        score = 0.0
        for kw in keywords:
            count = len(re.findall(r"\b" + re.escape(kw) + r"\b", text))
            score += count
        return score
