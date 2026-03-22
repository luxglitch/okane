"""
LLM signal enhancement.

Takes a raw strategy signal and uses Claude to validate and adjust confidence.
Only called for top signals to control costs.
"""
from typing import Optional
import structlog

from ..strategies.base import StrategySignal
from .client import LLMClient
from .prompts import SIGNAL_ENHANCEMENT_PROMPT

log = structlog.get_logger()


class SignalEnhancer:
    def __init__(self, llm: LLMClient, chroma_store=None):
        self.llm = llm
        self.chroma_store = chroma_store

    async def enhance(
        self,
        signal: StrategySignal,
        market_data: dict,
    ) -> StrategySignal:
        """
        Use LLM to validate/adjust a signal. Returns the signal (possibly modified).
        On LLM failure, returns original signal unchanged.
        """
        title = market_data.get("title") or signal.market_ticker
        yes_price = float(market_data.get("yes_bid") or market_data.get("last_price") or 0.5)
        yes_pct = yes_price * 100

        # Fetch RAG context from ChromaDB
        rag_context = "No historical context available."
        if self.chroma_store:
            try:
                similar = await self.chroma_store.query_similar_trades(title, n_results=3)
                if similar:
                    lines = []
                    for s in similar:
                        outcome = s.get("outcome", "unknown")
                        lines.append(
                            f"- Similar market: {s.get('title', '?')} → {outcome}: {s.get('lesson', '')}"
                        )
                    rag_context = "\n".join(lines)
            except Exception as exc:
                log.warning("rag_query_error", error=str(exc))

        prompt = SIGNAL_ENHANCEMENT_PROMPT.format(
            title=title,
            yes_price=yes_price,
            yes_pct=yes_pct,
            strategy_name=signal.strategy_name,
            confidence=signal.confidence,
            reasoning=signal.reasoning,
            rag_context=rag_context,
        )

        cache_key = f"{signal.market_ticker}:{signal.side}:{int(signal.confidence * 10)}"
        result = await self.llm.complete(
            prompt=prompt,
            purpose="signal_enhance",
            market_ticker=signal.market_ticker,
            cache_key=cache_key,
        )

        if not result:
            return signal

        adjusted_confidence = result.get("adjusted_confidence", signal.confidence)
        direction_confirmed = result.get("direction_confirmed", True)
        llm_reasoning = result.get("reasoning", "")
        key_risks = result.get("key_risks", [])

        if not direction_confirmed:
            log.info("llm_reversed_signal", ticker=signal.market_ticker, strategy=signal.strategy_name)
            # Flip the side and reduce confidence
            new_side = "no" if signal.side == "yes" else "yes"
            return StrategySignal(
                market_ticker=signal.market_ticker,
                side=new_side,
                confidence=round(float(adjusted_confidence) * 0.8, 4),
                raw_score=signal.raw_score,
                reasoning=f"[LLM reversed] {llm_reasoning}",
                strategy_name=signal.strategy_name,
                metadata={
                    **signal.metadata,
                    "llm_enhanced": True,
                    "key_risks": key_risks,
                },
            )

        return StrategySignal(
            market_ticker=signal.market_ticker,
            side=signal.side,
            confidence=round(float(adjusted_confidence), 4),
            raw_score=signal.raw_score,
            reasoning=f"{signal.reasoning} [LLM: {llm_reasoning}]",
            strategy_name=signal.strategy_name,
            metadata={
                **signal.metadata,
                "llm_enhanced": True,
                "key_risks": key_risks,
            },
        )
