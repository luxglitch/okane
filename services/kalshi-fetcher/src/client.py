import base64
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

import httpx
import structlog
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from .config import settings

log = structlog.get_logger()


class KalshiClient:
    def __init__(self):
        self._http = httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=httpx.Timeout(30.0),
            headers={"Content-Type": "application/json"},
        )
        self._private_key = None
        if settings.private_key_pem:
            self._private_key = serialization.load_pem_private_key(
                settings.private_key_pem,
                password=None,
            )

    async def close(self):
        await self._http.aclose()

    def _sign_request(self, method: str, path: str) -> dict:
        if not self._private_key or not settings.kalshi_api_key_id:
            return {}

        ts_ms = str(int(time.time() * 1000))
        # Strip query string from path for signing
        parsed = urlparse(path)
        path_no_query = parsed.path

        message = (ts_ms + method.upper() + path_no_query).encode("utf-8")
        signature = self._private_key.sign(
            message,
            asym_padding.PSS(
                mgf=asym_padding.MGF1(hashes.SHA256()),
                salt_length=asym_padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        sig_b64 = base64.b64encode(signature).decode("utf-8")

        return {
            "KALSHI-ACCESS-KEY": settings.kalshi_api_key_id,
            "KALSHI-ACCESS-SIGNATURE": sig_b64,
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
        }

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def _request(self, method: str, path: str, **kwargs) -> dict:
        auth_headers = self._sign_request(method, path)
        response = await self._http.request(
            method,
            path,
            headers=auth_headers,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    async def get_markets(
        self,
        cursor: Optional[str] = None,
        limit: int = 100,
        status: str = "open",
    ) -> dict:
        params = {"limit": limit, "status": status}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/markets", params=params)

    async def get_market(self, ticker: str) -> dict:
        return await self._request("GET", f"/markets/{ticker}")

    async def get_orderbook(self, ticker: str, depth: int = 10) -> dict:
        return await self._request(
            "GET", f"/markets/{ticker}/orderbook", params={"depth": depth}
        )

    async def get_all_markets(self, status: str = "open") -> list[dict]:
        """Paginate through all markets."""
        markets = []
        cursor = None
        while True:
            resp = await self.get_markets(cursor=cursor, limit=200, status=status)
            batch = resp.get("markets", [])
            markets.extend(batch)
            cursor = resp.get("cursor")
            if not cursor or not batch:
                break
        return markets

    async def get_markets_by_series(self, series_list: list[str], limit_per_series: int = 200) -> list[dict]:
        """Fetch all open markets for specific series tickers only."""
        results = []
        series_set = set(s.upper() for s in series_list)
        for series in series_list:
            try:
                resp = await self._request("GET", "/markets", params={
                    "series_ticker": series, "limit": limit_per_series, "status": "open"
                })
                for m in resp.get("markets", []):
                    et = (m.get("event_ticker") or "").split("-")[0].upper()
                    if et in series_set:
                        results.append(m)
            except Exception as exc:
                log.warning("series_fetch_error", series=series, error=str(exc))
        return results

    async def discover_prediction_tickers(self, target: int = 500, max_fetch: int = 15000) -> list[str]:
        """One-time deep scan to find non-parlay market tickers. Slow but only run occasionally."""
        tickers = []
        cursor = None
        scanned = 0
        while scanned < max_fetch and len(tickers) < target:
            resp = await self.get_markets(cursor=cursor, limit=200, status="open")
            batch = resp.get("markets", [])
            if not batch:
                break
            scanned += len(batch)
            for m in batch:
                et = m.get("event_ticker") or ""
                if not et.startswith("KXMV"):
                    tickers.append(m["ticker"])
            cursor = resp.get("cursor")
            if not cursor:
                break
        return tickers[:target]

    async def get_markets_by_tickers(self, tickers: list[str]) -> list[dict]:
        """Fetch current data for a known list of tickers."""
        results = []
        for ticker in tickers:
            try:
                m = await self.get_market(ticker)
                results.append(m.get("market", m))
            except Exception:
                pass
        return results

    async def get_markets_page_limited(self, status: str = "open", max_markets: int = 500) -> list[dict]:
        """Paginate up to max_markets — avoids fetching thousands of results."""
        markets = []
        cursor = None
        while len(markets) < max_markets:
            resp = await self.get_markets(cursor=cursor, limit=200, status=status)
            batch = resp.get("markets", [])
            markets.extend(batch)
            cursor = resp.get("cursor")
            if not cursor or not batch:
                break
        return markets[:max_markets]
