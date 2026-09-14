"""Strategy Risk/Reward metrics and Breakeven root finder."""

from typing import Any, List, Optional, Tuple


def calculate_breakevens(prices: List[float], pnls: List[float]) -> List[float]:
    """Find exact breakeven prices where P&L crosses zero via linear interpolation."""
    breakevens: List[float] = []
    for i in range(len(pnls) - 1):
        if (pnls[i] <= 0 and pnls[i + 1] >= 0) or (pnls[i] >= 0 and pnls[i + 1] <= 0):
            if pnls[i + 1] != pnls[i]:
                be = prices[i] + (0.0 - pnls[i]) * (prices[i + 1] - prices[i]) / (pnls[i + 1] - pnls[i])
                be = round(be, 2)
                if not any(abs(be - existing) < 0.05 for existing in breakevens):
                    breakevens.append(be)
    return breakevens


def calculate_risk_reward(pnls: List[float], legs: List[Any] | None = None) -> Tuple[float, Optional[float], Optional[float]]:
    """Compute max risk dollars, max profit dollars, and risk/reward ratio from P&L array.

    Analytically detects unlimited profit (unhedged long call) and unlimited loss (unhedged short call).
    :return: Tuple of (max_risk_dollars, max_profit_dollars, risk_reward_ratio)
    """
    if not pnls:
        return 0.0, 0.0, None

    max_profit = max(pnls)
    max_loss = min(pnls)

    has_unlimited_upside = False
    has_unlimited_downside_risk = False

    if legs:
        call_delta_at_inf = sum(
            (1 if leg.action.lower() in ("buy", "long") else -1) * leg.quantity
            for leg in legs if leg.option_type.lower() == "call"
        )
        if call_delta_at_inf > 0:
            has_unlimited_upside = True
        elif call_delta_at_inf < 0:
            has_unlimited_downside_risk = True

    max_risk_dollars = float("inf") if has_unlimited_downside_risk else (abs(max_loss) if max_loss < 0 else 0.0)
    max_profit_dollars = None if has_unlimited_upside else round(max_profit, 2)

    rr_ratio = None
    if max_risk_dollars > 0 and max_risk_dollars < 1e9 and max_profit_dollars is not None:
        rr_ratio = round(max_profit_dollars / max_risk_dollars, 2)

    return round(max_risk_dollars, 2) if max_risk_dollars < 1e9 else 999999.0, max_profit_dollars, rr_ratio
