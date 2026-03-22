"""
Core portfolio logic for paper trading.

All financial state mutations go through this class.
Every order placement and position close runs inside a single PostgreSQL
transaction to prevent race conditions.

--- FIXES (2026-03-22) ---
BUG 2 — get_portfolio() returned stale positions_value frozen at entry cost
         (sum(contracts * entry_price) from snapshot, never updated).
  Fix: get_portfolio() now queries open positions and joins with the markets
       table for current yes_bid / last_price, computing true mark-to-market
       positions_value and unrealized_pnl on every call. Falls back to 0.5
       if no current price is available.
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
import structlog

from .config import settings
from .models import (
    CloseResponse,
    FillResponse,
    OrderRequest,
    PortfolioResponse,
)
from .publisher import publish_fill, publish_close, publish_portfolio_snapshot
from .slippage import compute_fill_price, compute_fees, compute_slippage

log = structlog.get_logger()


class PaperPortfolio:
    def __init__(self, pool: asyncpg.Pool, redis):
        self.pool = pool
        self.redis = redis

    # ─── Portfolio State ─────────────────────────────────────────────────────

    async def ensure_initialized(self) -> None:
        """Insert the opening portfolio snapshot if none exists."""
        async with self.pool.acquire() as conn:
            count = await conn.fetchval("SELECT count(*) FROM portfolio_snapshots")
            if count == 0:
                await conn.execute(
                    """
                    INSERT INTO portfolio_snapshots
                        (ts, cash, positions_value, total_value, open_positions,
                         realized_pnl, unrealized_pnl, drawdown, peak_value)
                    VALUES ($1, $2, 0, $2, 0, 0, 0, 0, $2)
                    """,
                    datetime.now(timezone.utc),
                    settings.starting_balance,
                )
                log.info("portfolio_initialized", starting_balance=settings.starting_balance)

    async def get_cash(self, conn: asyncpg.Connection) -> float:
        row = await conn.fetchrow(
            "SELECT cash FROM portfolio_snapshots ORDER BY ts DESC LIMIT 1"
        )
        if row:
            return float(row["cash"])
        return settings.starting_balance

    async def get_portfolio(self) -> PortfolioResponse:
        async with self.pool.acquire() as conn:
            snap = await conn.fetchrow(
                "SELECT * FROM portfolio_snapshots ORDER BY ts DESC LIMIT 1"
            )
            # Join open positions with latest market snapshot for live MTM
            open_positions = await conn.fetch(
                """
                SELECT p.contracts, p.side, p.entry_price,
                       COALESCE(m.yes_bid, m.last_price) AS current_yes_price
                FROM positions p
                LEFT JOIN LATERAL (
                    SELECT yes_bid, last_price
                    FROM market_snapshots
                    WHERE market_ticker = p.market_ticker
                    ORDER BY ts DESC
                    LIMIT 1
                ) m ON true
                WHERE p.status = 'open'
                """
            )
            realized = await conn.fetchval(
                "SELECT COALESCE(sum(pnl), 0) FROM positions WHERE status = 'closed'"
            )

        cash = float(snap["cash"]) if snap else settings.starting_balance

        # Mark-to-market: value positions at current prices, not entry cost
        positions_value = 0.0
        unrealized_pnl = 0.0
        for pos in open_positions:
            current_yes = float(pos["current_yes_price"] or 0.5)
            current_price = current_yes if pos["side"] == "yes" else round(1.0 - current_yes, 4)
            contracts = int(pos["contracts"])
            entry_price = float(pos["entry_price"])
            mtm_value = contracts * current_price
            entry_value = contracts * entry_price
            positions_value += mtm_value
            unrealized_pnl += mtm_value - entry_value

        total_value = cash + positions_value
        pnl = total_value - settings.starting_balance
        pnl_pct = (pnl / settings.starting_balance) * 100 if settings.starting_balance else 0

        return PortfolioResponse(
            cash=cash,
            positions_value=positions_value,
            total_value=total_value,
            realized_pnl=float(realized or 0),
            unrealized_pnl=unrealized_pnl,
            pnl_percent=round(pnl_pct, 4),
            open_positions=len(open_positions),
            starting_balance=settings.starting_balance,
        )

    # ─── Order Placement ─────────────────────────────────────────────────────

    async def place_order(self, order: OrderRequest) -> FillResponse:
        slippage = compute_slippage(order.contracts, order.side, order.limit_price)
        fill_price = compute_fill_price(order.limit_price, slippage, order.side)
        fees = compute_fees(order.contracts)

        # Cost: contracts × fill_price (each contract is $1 par, price is fraction)
        cost = order.contracts * fill_price + fees
        now = datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                cash = await self.get_cash(conn)
                if cash < cost:
                    raise ValueError(
                        f"Insufficient cash: need ${cost:.4f}, have ${cash:.4f}"
                    )

                new_cash = cash - cost

                # Insert position
                position_id = await conn.fetchval(
                    """
                    INSERT INTO positions (
                        opened_at, market_ticker, side, contracts,
                        entry_price, slippage_paid, fees_paid, status, signal_id
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,'open',$8)
                    RETURNING id
                    """,
                    now,
                    order.market_ticker,
                    order.side,
                    order.contracts,
                    fill_price,
                    slippage,
                    fees,
                    order.signal_id,
                )

                # Recalculate positions_value after new position
                positions_value = await conn.fetchval(
                    "SELECT COALESCE(sum(contracts * entry_price), 0) FROM positions WHERE status='open'"
                )

                # Insert portfolio snapshot
                await conn.execute(
                    """
                    INSERT INTO portfolio_snapshots
                        (ts, cash, positions_value, total_value, open_positions,
                         realized_pnl, unrealized_pnl)
                    VALUES ($1, $2, $3, $4,
                        (SELECT count(*) FROM positions WHERE status='open'),
                        (SELECT COALESCE(sum(pnl), 0) FROM positions WHERE status='closed'),
                        $3)
                    """,
                    now,
                    new_cash,
                    float(positions_value or 0),
                    new_cash + float(positions_value or 0),
                )

        fill = FillResponse(
            position_id=position_id,
            market_ticker=order.market_ticker,
            side=order.side,
            contracts=order.contracts,
            fill_price=fill_price,
            slippage=slippage,
            fees=fees,
            cash_remaining=new_cash,
            timestamp=now,
        )

        # Publish to Redis
        try:
            await publish_fill(self.redis, {
                "position_id": str(position_id),
                "market_ticker": order.market_ticker,
                "side": order.side,
                "contracts": order.contracts,
                "fill_price": fill_price,
                "cash_remaining": new_cash,
                "ts": now,
            })
            await self._publish_portfolio_snapshot(new_cash, float(positions_value or 0))
        except Exception as exc:
            log.warning("redis_publish_error", error=str(exc))

        log.info(
            "order_placed",
            position_id=str(position_id),
            ticker=order.market_ticker,
            side=order.side,
            contracts=order.contracts,
            fill_price=fill_price,
        )
        return fill

    # ─── Position Closing ────────────────────────────────────────────────────

    async def close_position(
        self, position_id: UUID, exit_price: float, close_reason: str = "manual"
    ) -> CloseResponse:
        now = datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            pos = await conn.fetchrow(
                "SELECT * FROM positions WHERE id=$1 AND status='open'",
                position_id,
            )
            if not pos:
                raise ValueError(f"No open position found: {position_id}")

            # PnL: for YES contracts, payout is $1.00 if correct, $0.00 if not.
            # On close before settlement, we use market price.
            # contracts * (exit_price - entry_price) = unrealized PnL
            entry = float(pos["entry_price"])
            contracts = int(pos["contracts"])
            slippage = compute_slippage(contracts, pos["side"], exit_price)
            actual_exit = max(0.01, min(0.99, exit_price - slippage))
            fees = compute_fees(contracts)

            pnl = contracts * (actual_exit - entry) - fees
            proceeds = contracts * actual_exit - fees

            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE positions SET
                        closed_at=$1, exit_price=$2, pnl=$3,
                        status='closed', close_reason=$4
                    WHERE id=$5
                    """,
                    now,
                    actual_exit,
                    pnl,
                    close_reason,
                    position_id,
                )

                cash = await self.get_cash(conn)
                new_cash = cash + proceeds

                positions_value = await conn.fetchval(
                    "SELECT COALESCE(sum(contracts * entry_price), 0) FROM positions WHERE status='open'"
                )

                await conn.execute(
                    """
                    INSERT INTO portfolio_snapshots
                        (ts, cash, positions_value, total_value, open_positions,
                         realized_pnl, unrealized_pnl)
                    VALUES ($1,$2,$3,$4,
                        (SELECT count(*) FROM positions WHERE status='open'),
                        (SELECT COALESCE(sum(pnl), 0) FROM positions WHERE status='closed'),
                        $3)
                    """,
                    now,
                    new_cash,
                    float(positions_value or 0),
                    new_cash + float(positions_value or 0),
                )

        result = CloseResponse(
            position_id=position_id,
            market_ticker=pos["market_ticker"],
            side=pos["side"],
            contracts=contracts,
            entry_price=entry,
            exit_price=actual_exit,
            pnl=pnl,
            cash_remaining=new_cash,
            timestamp=now,
        )

        try:
            await publish_close(self.redis, {
                "position_id": str(position_id),
                "market_ticker": pos["market_ticker"],
                "side": pos["side"],
                "pnl": pnl,
                "exit_price": actual_exit,
                "ts": now,
            })
            await self._publish_portfolio_snapshot(new_cash, float(positions_value or 0))
        except Exception as exc:
            log.warning("redis_publish_error", error=str(exc))

        return result

    async def _publish_portfolio_snapshot(self, cash: float, positions_value: float) -> None:
        total = cash + positions_value
        pnl = total - settings.starting_balance
        pnl_pct = (pnl / settings.starting_balance) * 100 if settings.starting_balance else 0
        await publish_portfolio_snapshot(self.redis, {
            "cash": cash,
            "positions_value": positions_value,
            "total_value": total,
            "pnl_percent": round(pnl_pct, 4),
            "ts": datetime.now(timezone.utc),
        })
