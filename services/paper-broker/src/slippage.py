"""
Slippage model for paper trading.

Simulates realistic price impact based on order size.
Kalshi markets have relatively thin books, so we model:
  - Base slippage: 0.001 per contract for first 10 contracts
  - Incremental: 0.0005 per additional 10 contracts
  - Random noise: uniform(-0.001, 0.001)
  - Hard cap: 0.02 (2 cents) total slippage
"""
import random


def compute_slippage(contracts: int, side: str, limit_price: float) -> float:
    """
    Returns slippage in dollars per contract (added to buy price, subtracted from sell).
    For YES buys: you pay slightly more than the quoted price.
    For NO buys: same.
    """
    base = min(contracts, 10) * 0.001
    extra = max(0, contracts - 10) / 10 * 0.0005
    noise = random.uniform(-0.001, 0.001)
    total = base + extra + noise
    # Cap and floor
    total = max(0, min(total, 0.02))
    return round(total, 4)


def compute_fees(contracts: int) -> float:
    """
    Kalshi charges roughly $0.01 per contract, capped at $100 per order.
    We model a simplified flat fee.
    """
    return round(min(contracts * 0.01, 100.0), 4)


def compute_fill_price(limit_price: float, slippage: float, side: str) -> float:
    """
    Buyer pays limit_price + slippage.
    """
    fill = limit_price + slippage
    return round(max(0.01, min(0.99, fill)), 4)
