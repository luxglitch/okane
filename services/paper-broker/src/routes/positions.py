from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from ..models import PositionResponse

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("", response_model=list[PositionResponse])
async def list_positions(
    request: Request,
    status: Optional[str] = Query(None, pattern="^(open|closed|expired)$"),
    limit: int = Query(50, ge=1, le=500),
):
    pool = request.app.state.pool
    query = "SELECT * FROM positions"
    args = []
    if status:
        query += " WHERE status=$1"
        args.append(status)
    query += " ORDER BY opened_at DESC LIMIT $" + str(len(args) + 1)
    args.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *args)

    return [PositionResponse(**dict(row)) for row in rows]


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(position_id: UUID, request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM positions WHERE id=$1", position_id
        )
    if not row:
        raise HTTPException(status_code=404, detail="Position not found")
    return PositionResponse(**dict(row))
