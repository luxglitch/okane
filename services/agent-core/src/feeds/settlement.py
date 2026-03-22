"""
Settlement poller — fetches Kalshi market results for expired positions.

After a market's close_time passes, Kalshi publishes a `result` field ("yes" or "no").
We poll for this and close positions at full settlement price ($1.00 win / $0.00 loss).
"""
import base64
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog

from ..config import settings

log = structlog.get_logger()

_http: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(
            base_url=settings.kalshi_base_url,
            timeout=httpx.Timeout(10.0),
        )
    return _http


def _sign_headers(method: str, path: str) -> dict:
    """Returns auth headers if credentials are configured, else empty dict."""
    if not settings.kalshi_api_key_id or not settings.kalshi_private_key_b64:
        return {}
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding

        pem = base64.b64decode(settings.kalshi_private_key_b64)
        key = serialization.load_pem_private_key(pem, password=None)
        ts_ms = str(int(time.time() * 1000))
        message = (ts_ms + method.upper() + path).encode("utf-8")
        sig = key.sign(
            message,
            asym_padding.PSS(
                mgf=asym_padding.MGF1(hashes.SHA256()),
                salt_length=asym_padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": settings.kalshi_api_key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
        }
    except Exception:
        return {}


async def fetch_market_result(ticker: str) -> Optional[str]:
    """
    Returns "yes", "no", or None (not settled yet / error).
    """
    path = f"/markets/{ticker}"
    try:
        client = _get_client()
        resp = await client.get(path, headers=_sign_headers("GET", path))
        resp.raise_for_status()
        data = resp.json()
        market = data.get("market", data)
        result = market.get("result", "")
        if result in ("yes", "no"):
            return result
        return None
    except Exception as exc:
        log.debug("settlement_fetch_error", ticker=ticker, error=str(exc))
        return None


async def settle_expired_positions(pool, broker) -> list[dict]:
    """
    Find open positions whose market has expired, fetch results from Kalshi,
    and close them at settlement price. Returns list of settled positions.
    """
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        expired = await conn.fetch(
            """
            SELECT p.id, p.market_ticker, p.side, p.contracts, p.entry_price
            FROM positions p
            JOIN (
                SELECT DISTINCT ON (market_ticker) market_ticker, close_time
                FROM market_snapshots
                ORDER BY market_ticker, ts DESC
            ) m ON m.market_ticker = p.market_ticker
            WHERE p.status = 'open'
              AND m.close_time < $1
            """,
            now,
        )

    settled = []
    for pos in expired:
        ticker = pos["market_ticker"]
        result = await fetch_market_result(ticker)
        if result is None:
            continue  # Not settled yet or API error

        side = pos["side"]
        won = (side == result)
        settlement_price = 1.0 if won else 0.01  # $0.01 floor so broker math works

        try:
            await broker.close_position(pos["id"], settlement_price, close_reason="settlement")

            # Record in market_outcomes for post-mortem
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO market_outcomes (market_ticker, result, settled_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (market_ticker) DO NOTHING
                    """,
                    ticker, result, now,
                )

            log.info(
                "position_settled",
                ticker=ticker,
                side=side,
                result=result,
                won=won,
                settlement_price=settlement_price,
            )
            settled.append({"market_ticker": ticker, "result": result, "won": won})

        except Exception as exc:
            log.warning("settlement_close_error", ticker=ticker, error=str(exc))

    return settled
