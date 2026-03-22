"""
ChromaDB client wrapper.

Collections:
- market_patterns: normalized price vectors + settlement outcomes
- post_mortems: LLM-generated trade analysis text (semantic search)
- market_context: event descriptions + outcomes
"""
from typing import Optional
import chromadb
import structlog

log = structlog.get_logger()


class ChromaStore:
    def __init__(self, host: str, port: int):
        self._client = chromadb.HttpClient(host=host, port=port)
        self._patterns = None
        self._post_mortems = None
        self._context = None

    def _get_collection(self, name: str):
        return self._client.get_or_create_collection(name=name)

    @property
    def patterns(self):
        if self._patterns is None:
            self._patterns = self._get_collection("market_patterns")
        return self._patterns

    @property
    def post_mortems(self):
        if self._post_mortems is None:
            self._post_mortems = self._get_collection("post_mortems")
        return self._post_mortems

    @property
    def context(self):
        if self._context is None:
            self._context = self._get_collection("market_context")
        return self._context

    async def store_pattern(
        self,
        doc_id: str,
        pattern_vector: list[float],
        outcome: str,
        metadata: dict,
    ) -> None:
        try:
            self.patterns.upsert(
                ids=[doc_id],
                embeddings=[pattern_vector],
                documents=[outcome],
                metadatas=[{"outcome": outcome, **metadata}],
            )
        except Exception as exc:
            log.warning("chroma_store_pattern_error", error=str(exc))

    async def query_similar_patterns(
        self,
        pattern_vector: list[float],
        n_results: int = 10,
    ) -> list[dict]:
        try:
            results = self.patterns.query(
                query_embeddings=[pattern_vector],
                n_results=min(n_results, self.patterns.count() or 1),
            )
            if not results or not results.get("ids"):
                return []
            items = []
            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                items.append({
                    "id": doc_id,
                    "outcome": meta.get("outcome"),
                    "ticker": meta.get("ticker"),
                    "distance": results["distances"][0][i] if results.get("distances") else None,
                })
            return items
        except Exception as exc:
            log.warning("chroma_query_patterns_error", error=str(exc))
            return []

    async def store_post_mortem(
        self,
        doc_id: str,
        analysis_text: str,
        metadata: dict,
    ) -> None:
        try:
            self.post_mortems.upsert(
                ids=[doc_id],
                documents=[analysis_text],
                metadatas=[metadata],
            )
        except Exception as exc:
            log.warning("chroma_store_mortem_error", error=str(exc))

    async def query_similar_trades(
        self,
        market_title: str,
        n_results: int = 3,
    ) -> list[dict]:
        try:
            count = self.post_mortems.count()
            if count == 0:
                return []
            results = self.post_mortems.query(
                query_texts=[market_title],
                n_results=min(n_results, count),
            )
            if not results or not results.get("ids"):
                return []
            items = []
            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                items.append({
                    "id": doc_id,
                    "title": meta.get("title"),
                    "outcome": meta.get("outcome"),
                    "lesson": meta.get("lessons_learned"),
                    "was_correct": meta.get("was_correct"),
                })
            return items
        except Exception as exc:
            log.warning("chroma_query_trades_error", error=str(exc))
            return []
