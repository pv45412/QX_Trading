"""Poor Man's Covered Call (PMCC) Strategy Module."""

from typing import Any
from qx.strategies.base import BaseStrategyModule, StrategyContext, TradeProposal


class PMCCModule(BaseStrategyModule):
    @property
    def name(self) -> str:
        return "Poor Man's Covered Call (PMCC)"

    def evaluate_compatibility(self, context: StrategyContext) -> float:
        # PMCC favors moderate bullish direction (55-80) with low IV rank (< 45)
        if context.direction_score < 50.0:
            return 0.0

        dir_fit = (context.direction_score - 50.0) * 2.0
        vol_fit = max(0.0, 100.0 - context.iv_rank)
        score = (0.5 * dir_fit) + (0.5 * vol_fit)
        return round(min(100.0, max(0.0, score)), 2)

    def construct_trade(self, context: StrategyContext, chain_data: dict[str, Any]) -> TradeProposal | None:
        price = context.underlying_price
        long_strike = round(price * 0.85, 2)   # Deep ITM Long Call (365 DTE, delta ~0.80)
        short_strike = round(price * 1.05, 2)  # OTM Short Call (30 DTE, delta ~0.30)

        long_premium = price * 0.22
        short_premium = price * 0.03
        net_debit = round(long_premium - short_premium, 2)

        return TradeProposal(
            strategy_name=self.name,
            symbol=context.symbol,
            expiration="Long: 365DTE / Short: 30DTE",
            dte=30,
            legs=[
                {"side": "BUY", "type": "CALL", "strike": long_strike, "dte": 365, "delta": 0.80},
                {"side": "SELL", "type": "CALL", "strike": short_strike, "dte": 30, "delta": 0.30},
            ],
            entry_debit_credit=net_debit,
            max_risk_dollars=net_debit * 100.0,
            max_profit_dollars=round((short_strike - long_strike - net_debit) * 100.0, 2),
            break_even_price=round(long_strike + net_debit, 2),
            invalidation_price=round(price * 0.92, 2),
            target_price=short_strike,
            quality_grade="A",
        )
