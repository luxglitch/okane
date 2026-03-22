"""
Kelly Criterion position sizing.

For binary prediction markets (Kalshi):
  - YES contract: pay `price`, receive $1.00 if correct, $0.00 if wrong
  - Net odds b = (1 - price) / price
  - Kelly formula: f* = (b * p - q) / b   where q = 1 - p

We use 1/4 Kelly (fractional Kelly) for safety and cap at 5% of bankroll.
"""


def kelly_fraction(p_win: float, price: float) -> float:
    """
    p_win: probability of winning (from strategy confidence)
    price: cost of the contract (0.01 to 0.99)

    Returns fraction of bankroll to bet (0.0 to max_fraction).
    """
    price = max(0.01, min(0.99, price))
    p_win = max(0.01, min(0.99, p_win))
    q_win = 1.0 - p_win

    # Net odds: win (1 - price), lose (price)
    b = (1.0 - price) / price

    # Full Kelly
    f_full = (b * p_win - q_win) / b

    # Quarter-Kelly for safety
    f_quarter = f_full * 0.25

    # Hard cap at 5% of bankroll per trade
    return max(0.0, min(f_quarter, 0.05))


def compute_contracts(
    bankroll: float,
    kelly_f: float,
    price: float,
    min_contracts: int = 1,
    max_contracts: int = 200,
) -> int:
    """
    Convert Kelly fraction to a number of contracts.

    bankroll: total portfolio value in dollars
    kelly_f: fraction from kelly_fraction()
    price: fill price per contract
    """
    if kelly_f <= 0 or price <= 0:
        return 0

    dollar_amount = bankroll * kelly_f
    contracts = int(dollar_amount / price)
    return max(min_contracts, min(contracts, max_contracts))
