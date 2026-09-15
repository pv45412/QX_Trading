"""Account-Equity Position Sizing Engine for QX Platform.

CRITICAL FINANCIAL SAFETY PRINCIPLES:
1. Sizes positions strictly from Net Liquidation Account Equity and defined strategy max loss.
2. Long Option max risk = Option Premium * 100 multiplier.
3. Defined-Risk Spread max risk = Analytical Spread Max Loss.
4. NEVER sizes trades based on available buying power alone.
5. NO FALLBACK SIZING: Invalid/undefined stop or max loss returns recommended_units = 0 (Fail Closed).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PositionSizingResult:
    symbol: str
    account_equity: float
    max_risk_pct_per_trade: float
    max_allowable_dollar_risk: float
    max_loss_per_unit: float
    recommended_units: int  # Shares or Contracts
    total_dollar_risk: float
    capital_required: float
    is_buying_power_sufficient: bool
    is_valid: bool
    summary: str


class AccountEquityPositionSizer:
    """Calculates position sizes based on equity risk budget and strategy max loss."""

    def __init__(self, default_max_risk_pct: float = 0.50) -> None:
        self.default_max_risk_pct = default_max_risk_pct  # 0.50% default risk per trade

    def calculate_position_size(
        self,
        symbol: str,
        account_equity: float,
        buying_power: float,
        entry_price: float,
        stop_loss_price: Optional[float] = None,
        max_loss_override_per_contract: Optional[float] = None,
        is_option_strategy: bool = True,
        unit_multiplier: int = 100,  # 100 for options, 1 for shares
        max_risk_pct_per_trade: float = 0.50,
    ) -> PositionSizingResult:
        if account_equity <= 0:
            return PositionSizingResult(
                symbol=symbol,
                account_equity=account_equity,
                max_risk_pct_per_trade=max_risk_pct_per_trade,
                max_allowable_dollar_risk=0.0,
                max_loss_per_unit=0.0,
                recommended_units=0,
                total_dollar_risk=0.0,
                capital_required=0.0,
                is_buying_power_sufficient=False,
                is_valid=False,
                summary=f"Position Sizing INVALID for {symbol}: Account equity <= 0.",
            )

        risk_pct = max(0.01, min(5.0, max_risk_pct_per_trade))
        max_allowable_dollar_risk = round(account_equity * (risk_pct / 100.0), 2)

        # 1. Determine unit max loss
        if max_loss_override_per_contract is not None and max_loss_override_per_contract > 0:
            # Analytical spread max loss override provided
            max_loss_per_unit = float(max_loss_override_per_contract)
        elif is_option_strategy:
            # Long option strategy max loss = premium * multiplier
            if entry_price <= 0:
                max_loss_per_unit = 0.0
            else:
                max_loss_per_unit = entry_price * unit_multiplier
        else:
            # Stock position sizing based on stop loss distance
            if entry_price <= 0 or stop_loss_price is None or stop_loss_price <= 0 or stop_loss_price == entry_price:
                # FAIL-CLOSED: No 5% fallback!
                max_loss_per_unit = 0.0
            else:
                max_loss_per_unit = abs(entry_price - stop_loss_price) * unit_multiplier

        # FAIL-CLOSED: If max loss per unit is non-positive, return zero units
        if max_loss_per_unit <= 0:
            return PositionSizingResult(
                symbol=symbol,
                account_equity=account_equity,
                max_risk_pct_per_trade=risk_pct,
                max_allowable_dollar_risk=max_allowable_dollar_risk,
                max_loss_per_unit=0.0,
                recommended_units=0,
                total_dollar_risk=0.0,
                capital_required=0.0,
                is_buying_power_sufficient=False,
                is_valid=False,
                summary=f"Position Sizing FAIL-CLOSED for {symbol}: Defined strategy max loss is invalid or undefined.",
            )

        # Calculate allowed units based strictly on equity risk limit
        recommended_units = int(max_allowable_dollar_risk // max_loss_per_unit)
        if recommended_units < 1:
            recommended_units = 0

        total_dollar_risk = round(recommended_units * max_loss_per_unit, 2)
        capital_required = round(recommended_units * entry_price * unit_multiplier, 2)
        is_buying_power_sufficient = buying_power >= capital_required
        is_valid = recommended_units > 0 and is_buying_power_sufficient

        summary = (
            f"Position Sizing for {symbol}: Equity ${account_equity:,.2f} ({risk_pct:.2f}% max risk = ${max_allowable_dollar_risk:,.2f}). "
            f"Max Loss/Unit: ${max_loss_per_unit:,.2f} -> Recommended: {recommended_units} units (${capital_required:,.2f} required, BP ${buying_power:,.2f})."
        )

        return PositionSizingResult(
            symbol=symbol,
            account_equity=account_equity,
            max_risk_pct_per_trade=risk_pct,
            max_allowable_dollar_risk=max_allowable_dollar_risk,
            max_loss_per_unit=round(max_loss_per_unit, 2),
            recommended_units=recommended_units,
            total_dollar_risk=total_dollar_risk,
            capital_required=capital_required,
            is_buying_power_sufficient=is_buying_power_sufficient,
            is_valid=is_valid,
            summary=summary,
        )
