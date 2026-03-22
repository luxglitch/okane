"""
LLM client with provider abstraction, rate limiting, caching, and cost tracking.

Supported providers (set LLM_PROVIDER in .env):
  anthropic  — Anthropic Claude
  deepseek   — DeepSeek API
  llamacpp   — llama.cpp local server
"""
import asyncio
import json
import re
import time
from typing import Optional

import redis.asyncio as aioredis
import structlog

from ..config import settings
from .providers.base import BaseProvider
from .providers.factory import build_provider

log = structlog.get_logger()

RATE_LIMIT_KEY_MINUTE = "okane:llm:calls:minute"
RATE_LIMIT_KEY_DAY = "okane:llm:calls:day"


class LLMClient:
    def __init__(self, redis: aioredis.Redis, pool):
        self.redis = redis
        self.pool = pool
        self._provider: BaseProvider = build_provider(settings)

    async def _check_rate_limits(self) -> tuple[bool, str]:
        pipe = self.redis.pipeline()
        pipe.incr(RATE_LIMIT_KEY_MINUTE)
        pipe.expire(RATE_LIMIT_KEY_MINUTE, 60)
        pipe.incr(RATE_LIMIT_KEY_DAY)
        pipe.expire(RATE_LIMIT_KEY_DAY, 86400)
        results = await pipe.execute()

        minute_count = int(results[0])
        day_count = int(results[2])

        if minute_count > settings.llm_max_calls_per_minute:
            return False, f"Rate limit: {minute_count} calls this minute (max {settings.llm_max_calls_per_minute})"
        if day_count > settings.llm_max_calls_per_day:
            return False, f"Daily limit: {day_count} calls today (max {settings.llm_max_calls_per_day})"
        return True, "ok"

    async def _get_cached(self, cache_key: str) -> Optional[dict]:
        val = await self.redis.get(f"okane:llm:cache:{cache_key}")
        if val:
            return json.loads(val)
        return None

    async def _set_cached(self, cache_key: str, data: dict, ttl: int = 300) -> None:
        await self.redis.setex(f"okane:llm:cache:{cache_key}", ttl, json.dumps(data))

    def _parse_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            log.warning("llm_json_parse_error", text=text[:200])
            return {"raw": text}

    async def complete(
        self,
        prompt: str,
        purpose: str,
        market_ticker: Optional[str] = None,
        cache_key: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Call the configured LLM provider and return a parsed JSON dict.
        Returns None on rate limit or error.
        """
        # Check cache
        if cache_key:
            cached = await self._get_cached(cache_key)
            if cached:
                log.debug("llm_cache_hit", cache_key=cache_key, provider=self._provider.name)
                return cached

        # Rate limiting (skip for local providers — no cost to limit)
        if "llamacpp" not in self._provider.name:
            allowed, reason = await self._check_rate_limits()
            if not allowed:
                log.warning("llm_rate_limited", reason=reason)
                return None

        start = time.monotonic()
        try:
            # Provider.complete() is synchronous — run in thread executor
            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(
                None, lambda: self._provider.complete(prompt, max_tokens=1024)
            )
            latency_ms = int((time.monotonic() - start) * 1000)

            result = self._parse_json(resp.text)

            await self._log_call(
                model=resp.model,
                purpose=purpose,
                market_ticker=market_ticker,
                prompt_tokens=resp.prompt_tokens,
                completion_tokens=resp.completion_tokens,
                cost=resp.cost_usd,
                latency_ms=latency_ms,
                response_summary=resp.text[:200],
            )

            if cache_key:
                await self._set_cached(cache_key, result)

            log.info(
                "llm_call_complete",
                provider=self._provider.name,
                purpose=purpose,
                prompt_tokens=resp.prompt_tokens,
                completion_tokens=resp.completion_tokens,
                cost_usd=round(resp.cost_usd, 6),
                latency_ms=latency_ms,
            )
            return result

        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            log.error(
                "llm_call_error",
                provider=self._provider.name,
                purpose=purpose,
                error=str(exc),
                exc_info=True,
            )
            return None

    async def _log_call(
        self,
        model: str,
        purpose: str,
        market_ticker: Optional[str],
        prompt_tokens: int,
        completion_tokens: int,
        cost: float,
        latency_ms: int,
        response_summary: str,
    ) -> None:
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO llm_calls
                        (model, prompt_tokens, completion_tokens, total_cost_usd,
                         purpose, market_ticker, latency_ms, response_summary)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    """,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    cost,
                    purpose,
                    market_ticker,
                    latency_ms,
                    response_summary,
                )
        except Exception as exc:
            log.warning("llm_log_error", error=str(exc))
