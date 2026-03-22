"""
HTTP client for paper-broker REST API.
"""
from typing import Optional
from uuid import UUID

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import settings

log = structlog.get_logger()


class BrokerClient:
    def __init__(self):
        self._http = httpx.AsyncClient(
            base_url=settings.paper_broker_url,
            timeout=httpx.Timeout(15.0),
        )

    async def close(self):
        await self._http.aclose()

    @retry(
        wait=wait_exponential(min=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = await self._http.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    async def get_portfolio(self) -> dict:
        return await self._request("GET", "/portfolio")

    async def get_positions(self, status: Optional[str] = None) -> list[dict]:
        params = {}
        if status:
            params["status"] = status
        result = await self._request("GET", "/positions", params=params)
        return result if isinstance(result, list) else []

    async def place_order(
        self,
        market_ticker: str,
        side: str,
        contracts: int,
        limit_price: float,
        signal_id: Optional[str] = None,
    ) -> dict:
        payload = {
            "market_ticker": market_ticker,
            "side": side,
            "contracts": contracts,
            "order_type": "limit",
            "limit_price": limit_price,
        }
        if signal_id:
            payload["signal_id"] = signal_id
        return await self._request("POST", "/orders", json=payload)

    async def close_position(
        self,
        position_id: UUID,
        exit_price: float,
        close_reason: Optional[str] = None,
    ) -> dict:
        params: dict = {"exit_price": exit_price}
        if close_reason:
            params["close_reason"] = close_reason
        return await self._request("DELETE", f"/orders/{position_id}", params=params)
