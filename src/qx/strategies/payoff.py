"""Leg Payoff Engine for evaluating multi-leg option strategies and generating P&L curves."""

from typing import Any
from pydantic import BaseModel, Field


class OptionLeg(BaseModel):
    option_type: str = Field(..., description="'call' or 'put'")
    action: str = Field(..., description="'buy' or 'sell'")
    strike: float
    premium: float
    quantity: int = 1
    dte: int = 30


class PayoffCurvePoint(BaseModel):
    underlying_price: float
    pnl_dollars: float
    pnl_pct: float


class StrategyPayoffResult(BaseModel):
    strategy_name: str
    underlying_price: float
    net_debit_credit: float  # Positive = net debit paid, Negative = net credit received
    max_risk_dollars: float
    max_profit_dollars: float | None
    breakevens: list[float]
    risk_reward_ratio: float | None
    curve: list[PayoffCurvePoint]


def calculate_leg_payoff(leg: OptionLeg, spot_price: float) -> float:
    """Calculate at-expiration P&L in dollars for a single option leg at spot_price."""
    sign = 1 if leg.action.lower() in ("buy", "long") else -1
    
    if leg.option_type.lower() == "call":
        intrinsic = max(0.0, spot_price - leg.strike)
    else:  # put
        intrinsic = max(0.0, leg.strike - spot_price)
        
    # P&L per contract = (Intrinsic value - Initial premium paid/received) * sign * 100 * quantity
    pnl = (intrinsic - leg.premium) * sign * 100.0 * leg.quantity
    return pnl


def generate_strategy_payoff(
    strategy_name: str,
    underlying_price: float,
    legs: list[OptionLeg],
    num_points: int = 51,
    range_pct: float = 0.20
) -> StrategyPayoffResult:
    """Generate multi-leg option strategy payoff curve across a price range."""
    if not legs or underlying_price <= 0:
        return StrategyPayoffResult(
            strategy_name=strategy_name,
            underlying_price=underlying_price,
            net_debit_credit=0.0,
            max_risk_dollars=0.0,
            max_profit_dollars=0.0,
            breakevens=[],
            risk_reward_ratio=0.0,
            curve=[]
        )

    # Net debit (+) or credit (-)
    net_debit_credit = 0.0
    for leg in legs:
        sign = 1 if leg.action.lower() in ("buy", "long") else -1
        net_debit_credit += leg.premium * sign * 100.0 * leg.quantity

    min_price = max(0.5, underlying_price * (1.0 - range_pct))
    max_price = underlying_price * (1.0 + range_pct)
    step = (max_price - min_price) / (num_points - 1)

    curve: list[PayoffCurvePoint] = []
    pnls: list[float] = []
    prices: list[float] = []

    for i in range(num_points):
        price = round(min_price + i * step, 2)
        prices.append(price)
        
        total_pnl = sum(calculate_leg_payoff(leg, price) for leg in legs)
        pnls.append(total_pnl)
        
        # P&L % based on net debit if debit trade, or max risk if credit trade
        cost_basis = abs(net_debit_credit) if net_debit_credit != 0 else 100.0
        pnl_pct = round((total_pnl / cost_basis) * 100.0, 2)
        
        curve.append(PayoffCurvePoint(
            underlying_price=price,
            pnl_dollars=round(total_pnl, 2),
            pnl_pct=pnl_pct
        ))

    max_profit = max(pnls)
    max_loss = min(pnls)

    # Find breakevens where P&L crosses zero
    breakevens: list[float] = []
    for i in range(len(pnls) - 1):
        if (pnls[i] <= 0 and pnls[i + 1] >= 0) or (pnls[i] >= 0 and pnls[i + 1] <= 0):
            # Linear interpolation
            if pnls[i + 1] != pnls[i]:
                be = prices[i] + (0.0 - pnls[i]) * (prices[i + 1] - prices[i]) / (pnls[i + 1] - pnls[i])
                breakevens.append(round(be, 2))

    max_risk_dollars = abs(max_loss) if max_loss < 0 else 0.0
    
    # Cap absurd max profit numbers (e.g. naked calls) at None
    max_profit_dollars = round(max_profit, 2) if max_profit < 1e6 else None
    
    rr_ratio = None
    if max_risk_dollars > 0 and max_profit_dollars is not None:
        rr_ratio = round(max_profit_dollars / max_risk_dollars, 2)

    return StrategyPayoffResult(
        strategy_name=strategy_name,
        underlying_price=underlying_price,
        net_debit_credit=round(net_debit_credit, 2),
        max_risk_dollars=round(max_risk_dollars, 2),
        max_profit_dollars=max_profit_dollars,
        breakevens=breakevens,
        risk_reward_ratio=rr_ratio,
        curve=curve
    )
