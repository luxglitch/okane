from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StrategySignal:
    market_ticker: str
    side: str           # 'yes' or 'no'
    confidence: float   # 0.0 to 1.0
    raw_score: float
    reasoning: str
    strategy_name: str
    metadata: dict = field(default_factory=dict)


class BaseStrategy(ABC):
    name: str = "base"
    weight: float = 0.25

    @abstractmethod
    async def analyze(
        self,
        ticker: str,
        market_data: dict,
        price_history: list[dict],
    ) -> Optional[StrategySignal]:
        """
        Analyze a market and return a signal, or None if no signal.
        market_data: current market snapshot dict
        price_history: list of recent OHLC dicts from market_ohlc_5min
        """
        ...

    async def warmup(self, pool) -> None:
        """Load any historical data needed before the agent starts."""
        pass
