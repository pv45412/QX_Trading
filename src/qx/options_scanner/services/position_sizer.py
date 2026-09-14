"""Account-Equity Position Sizing Engine for QX Platform.

CRITICAL FINANCIAL SAFETY PRINCIPLE:
Sizes positions strictly from Net Liquidation Account Equity and defined stop-loss risk.
NEVER sizes trades based on available buying power alone.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PositionSizingResult:
    symbol: str
    account_equity: float
    max_risk_pct_per_trade: float
    max_allowable_dollar_risk: float
    stop_loss_risk_per_unit: float
    recommended_units: int  # Shares or Contracts
    total_dollar_risk: float
    capital_required: float
    is_buying_power_sufficient: bool
    summary: str


class AccountEquityPositionSizer:
    """Calculates position sizes based on equity risk budget and stop-loss distance."""

    def __init__(self, default_max_risk_pct: float = 0.50) -> None:
        self.default_max_risk_pct = default_max_risk_pct  # 0.50% default risk per trade

    def calculate_position_size(
        self,
        symbol: str,
        account_equity: float,
        buying_power: float,
        entry_price: float,
        stop_loss_price: float,
        unit_multiplier: int = 100,  # 100 for options, 1 for shares
        max_risk_pct_per_trade: float = 0.50,
    ) -> PositionSizingResult:
        if account_equity <= 0:
            raise ValueError("Account equity must be greater than zero for position sizing.")
        if entry_price <= 0 or stop_loss_price <= 0:
            raise ValueError("Entry price and stop loss price must be positive.")

        # Calculate max allowable dollar loss from Net Liquidation Equity
        risk_pct = max(0.01, min(5.0, max_risk_pct_per_trade))
        max_allowable_dollar_risk = round(account_equity * (risk_pct / 100.0), 2)

        # Risk per contract / share
        risk_per_share = abs(entry_price - stop_loss_price)
        if risk_per_share <= 0:
            risk_per_share = entry_price * 0.05  # Fallback 5% risk if stop equals entry

        risk_per_unit = risk_per_share * unit_multiplier

        # Calculate allowed units based strictly on equity risk limit
        recommended_units = int(max_allowable_dollar_risk // risk_per_unit)
        if recommended_units < 1:
            recommended_units = 0

        total_dollar_risk = round(recommended_units * risk_per_unit, 2)
        capital_required = round(recommended_units * entry_price * unit_multiplier, 2)
        is_buying_power_sufficient = buying_power >= capital_required

        summary = (
            f"Position Sizing for {symbol}: Equity ${account_equity:,.2f} ({risk_pct:.2f}% max risk = ${max_allowable_dollar_risk:,.2f}). "
            f"Risk/Unit: ${risk_per_unit:,.2f} -> Recommended: {recommended_units} units (${capital_required:,.2f} required, BP ${buying_power:,.2f})."
        )

        return PositionSizingResult(
            symbol=symbol,
            account_equity=account_equity,
            max_risk_pct_per_trade=risk_pct,
            max_allowable_dollar_risk=max_allowable_dollar_risk,
            stop_loss_risk_per_unit=round(risk_per_unit, 2),
            recommended_units=recommended_units,
            total_dollar_risk=total_dollar_risk,
            capital_required=capital_required,
            is_buying_power_sufficient=is_buying_power_sufficient,
            summary=summary,
        )
