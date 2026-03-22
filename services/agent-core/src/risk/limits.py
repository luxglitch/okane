"""
Portfolio-level risk checks.

Guards against: over-concentration, duplicate positions.
"""
import structlog

from ..config import settings

log = structlog.get_logger()


class RiskChecker:
    def check_signal(
        self,
        ticker: str,
        side: str,
        suggested_contracts: int,
        suggested_price: float,
        portfolio: dict,
        open_positions: list[dict],
    ) -> tuple[bool, str]:
        """
        Returns (approved: bool, reason: str).
        """
        cash = portfolio.get("cash", 0)
        total_value = portfolio.get("total_value", settings.starting_balance)

        # 1. Duplicate position check
        for pos in open_positions:
            if pos.get("market_ticker") == ticker and pos.get("side") == side:
                return False, f"Already have open {side} position on {ticker}"

        # 2. Cost check
        cost = suggested_contracts * suggested_price
        if cost > cash:
            return False, f"Insufficient cash (need ${cost:.2f}, have ${cash:.2f})"

        # 3. Max single position fraction
        cost_fraction = cost / total_value if total_value > 0 else 1.0
        if cost_fraction > settings.max_position_fraction:
            return False, (
                f"Position size {cost_fraction:.1%} exceeds max "
                f"{settings.max_position_fraction:.1%} of portfolio"
            )

        # 4. Min contracts sanity
        if suggested_contracts < 1:
            return False, "Kelly sizing produced 0 contracts"

        return True, "approved"
