from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class MarketSnapshot(BaseModel):
    ts: datetime
    market_ticker: str
    event_ticker: Optional[str] = None
    title: Optional[str] = None
    yes_bid: Optional[float] = None
    yes_ask: Optional[float] = None
    no_bid: Optional[float] = None
    no_ask: Optional[float] = None
    last_price: Optional[float] = None
    volume: int = 0
    open_interest: int = 0
    liquidity: Optional[float] = None
    status: Optional[str] = None
    close_time: Optional[datetime] = None
    result: Optional[str] = None
    raw_json: Optional[dict] = None


class KalshiMarket(BaseModel):
    ticker: str
    event_ticker: Optional[str] = None
    title: Optional[str] = None
    yes_bid: Optional[float] = Field(None, alias="yes_bid")
    yes_ask: Optional[float] = Field(None, alias="yes_ask")
    no_bid: Optional[float] = Field(None, alias="no_bid")
    no_ask: Optional[float] = Field(None, alias="no_ask")
    last_price: Optional[float] = None
    volume: int = 0
    open_interest: int = 0
    liquidity: Optional[float] = None
    status: Optional[str] = None
    close_time: Optional[datetime] = None
    result: Optional[str] = None

    model_config = {"populate_by_name": True}


class KalshiMarketsResponse(BaseModel):
    markets: list[KalshiMarket] = []
    cursor: Optional[str] = None
