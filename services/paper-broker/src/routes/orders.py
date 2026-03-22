from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from ..models import CloseResponse, FillResponse, OrderRequest
from ..portfolio import PaperPortfolio

router = APIRouter(prefix="/orders", tags=["orders"])


def get_portfolio(request: Request) -> PaperPortfolio:
    return request.app.state.portfolio


@router.post("", response_model=FillResponse, status_code=201)
async def place_order(
    order: OrderRequest,
    portfolio: PaperPortfolio = Depends(get_portfolio),
):
    try:
        return await portfolio.place_order(order)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{position_id}", response_model=CloseResponse)
async def close_position(
    position_id: UUID,
    exit_price: float,
    portfolio: PaperPortfolio = Depends(get_portfolio),
):
    try:
        return await portfolio.close_position(position_id, exit_price, close_reason="manual")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
