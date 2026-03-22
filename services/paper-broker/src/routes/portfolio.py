from typing import Optional

from fastapi import APIRouter, Query, Request

from ..models import PortfolioResponse, PortfolioSnapshotResponse

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioResponse)
async def get_portfolio(request: Request):
    return await request.app.state.portfolio.get_portfolio()


@router.get("/history", response_model=list[PortfolioSnapshotResponse])
async def get_history(
    request: Request,
    interval: str = Query("1h", pattern="^(5m|15m|1h|4h|1d)$"),
    limit: int = Query(200, ge=1, le=1000),
):
    pool = request.app.state.pool

    bucket_map = {
        "5m": "5 minutes",
        "15m": "15 minutes",
        "1h": "1 hour",
        "4h": "4 hours",
        "1d": "1 day",
    }
    bucket = bucket_map.get(interval, "1 hour")

    query = f"""
        SELECT
            time_bucket('{bucket}', ts) AS ts,
            last(cash, ts) AS cash,
            last(positions_value, ts) AS positions_value,
            last(total_value, ts) AS total_value,
            last(open_positions, ts) AS open_positions,
            last(realized_pnl, ts) AS realized_pnl,
            last(unrealized_pnl, ts) AS unrealized_pnl
        FROM portfolio_snapshots
        GROUP BY time_bucket('{bucket}', ts)
        ORDER BY ts DESC
        LIMIT $1
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, limit)

    return [PortfolioSnapshotResponse(**dict(row)) for row in reversed(rows)]
