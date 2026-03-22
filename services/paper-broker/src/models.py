from datetime import datetime
from typing import Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ─── Request Models ──────────────────────────────────────────────────────────

class OrderRequest(BaseModel):
    market_ticker: str
    side: Literal["yes", "no"]
    contracts: int = Field(ge=1)
    order_type: Literal["market", "limit"] = "limit"
    limit_price: float = Field(ge=0.01, le=0.99)
    signal_id: Optional[UUID] = None


# ─── Response Models ─────────────────────────────────────────────────────────

class FillResponse(BaseModel):
    position_id: UUID
    market_ticker: str
    side: str
    contracts: int
    fill_price: float
    slippage: float
    fees: float
    cash_remaining: float
    timestamp: datetime


class PositionResponse(BaseModel):
    id: UUID
    opened_at: datetime
    closed_at: Optional[datetime]
    market_ticker: str
    side: str
    contracts: int
    entry_price: float
    exit_price: Optional[float]
    slippage_paid: float
    fees_paid: float
    pnl: Optional[float]
    status: str
    close_reason: Optional[str]
    unrealized_pnl: Optional[float] = None


class PortfolioResponse(BaseModel):
    cash: float
    positions_value: float
    total_value: float
    realized_pnl: float
    unrealized_pnl: float
    pnl_percent: float
    open_positions: int
    starting_balance: float


class PortfolioSnapshotResponse(BaseModel):
    ts: datetime
    cash: float
    positions_value: float
    total_value: float
    open_positions: int
    realized_pnl: float
    unrealized_pnl: float


class CloseResponse(BaseModel):
    position_id: UUID
    market_ticker: str
    side: str
    contracts: int
    entry_price: float
    exit_price: float
    pnl: float
    cash_remaining: float
    timestamp: datetime
