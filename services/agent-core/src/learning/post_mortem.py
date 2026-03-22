"""
Post-mortem analysis triggered after market settlement.
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import asyncpg
import structlog

from ..llm.client import LLMClient
from ..llm.prompts import POST_MORTEM_PROMPT
from .chroma_client import ChromaStore

log = structlog.get_logger()


class PostMortemAnalyzer:
    def __init__(self, pool: asyncpg.Pool, llm: LLMClient, chroma: ChromaStore):
        self.pool = pool
        self.llm = llm
        self.chroma = chroma

    async def process_settlement(self, market_ticker: str, result: str) -> None:
        """
        Called when a market settles. Finds all closed positions for that market
        and generates post-mortem analysis.
        """
        async with self.pool.acquire() as conn:
            positions = await conn.fetch(
                """
                SELECT p.*, ts.reasoning, ts.strategy_name, m.title
                FROM positions p
                LEFT JOIN trade_signals ts ON ts.id = p.signal_id
                LEFT JOIN (
                    SELECT DISTINCT ON (market_ticker) market_ticker, title
                    FROM market_snapshots ORDER BY market_ticker, ts DESC
                ) m ON m.market_ticker = p.market_ticker
                WHERE p.market_ticker = $1 AND p.status = 'closed'
                """,
                market_ticker,
            )

        for pos in positions:
            await self._analyze_position(pos, result)

    async def _analyze_position(self, pos, market_result: str) -> None:
        position_id = pos["id"]
        side = pos["side"]
        was_correct = (side == market_result)
        outcome = "win" if was_correct else "loss"
        pnl = float(pos["pnl"] or 0)

        title = pos.get("title") or pos["market_ticker"]
        reasoning = pos.get("reasoning") or "No reasoning recorded"

        # RAG context
        similar = await self.chroma.query_similar_trades(title, n_results=3)
        rag_lines = [
            f"- {s.get('title', '?')}: {s.get('outcome', '?')} — {s.get('lesson', '')}"
            for s in similar
        ]
        rag_context = "\n".join(rag_lines) if rag_lines else "No historical context."

        prompt = POST_MORTEM_PROMPT.format(
            title=title,
            side=side,
            entry_price=float(pos["entry_price"]),
            contracts=int(pos["contracts"]),
            result=market_result,
            outcome=outcome,
            pnl=pnl,
            original_reasoning=reasoning,
            rag_context=rag_context,
        )

        result_json = await self.llm.complete(
            prompt=prompt,
            purpose="post_mortem",
            market_ticker=pos["market_ticker"],
        )

        analysis = ""
        lessons = ""
        if result_json:
            analysis = result_json.get("analysis", "")
            lessons = result_json.get("lessons_learned", "")

        # Store in DB
        mortem_id = str(uuid4())
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO post_mortems
                    (id, created_at, position_id, market_ticker, outcome,
                     was_correct, pnl, analysis, lessons_learned, embedding_id)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT DO NOTHING
                """,
                mortem_id,
                datetime.now(timezone.utc),
                position_id,
                pos["market_ticker"],
                outcome,
                was_correct,
                pnl,
                analysis,
                lessons,
                mortem_id,
            )

        # Store in ChromaDB for future RAG
        doc_text = f"{title}\n{analysis}\nLesson: {lessons}"
        await self.chroma.store_post_mortem(
            doc_id=mortem_id,
            analysis_text=doc_text,
            metadata={
                "ticker": pos["market_ticker"],
                "title": title,
                "outcome": outcome,
                "was_correct": was_correct,
                "pnl": pnl,
                "lessons_learned": lessons,
            },
        )

        log.info(
            "post_mortem_complete",
            ticker=pos["market_ticker"],
            outcome=outcome,
            was_correct=was_correct,
            pnl=pnl,
        )
