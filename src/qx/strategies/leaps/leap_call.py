"""LEAP Call Strategy Module (> 300 DTE, Delta >= 0.80)."""

from typing import Any
from qx.strategies.base import BaseStrategyModule, StrategyContext, TradeProposal


class LEAPCallModule(BaseStrategyModule):
    @property
    def name(self) -> str:
        return "LEAP Long Call"

    def evaluate_compatibility(self, context: StrategyContext) -> float:
        # LEAPs favor strong bullish direction (score > 65) and low/fair IV Rank (< 40)
        if context.direction_score < 50.0:
            return 0.0

        dir_fit = (context.direction_score - 50.0) * 2.0
        vol_fit = max(0.0, 100.0 - context.iv_rank)
        score = (0.6 * dir_fit) + (0.4 * vol_fit)
        return round(min(100.0, max(0.0, score)), 2)

    def construct_trade(self, context: StrategyContext, chain_data: dict[str, Any]) -> TradeProposal | None:
        price = context.underlying_price
        strike = round(price * 0.85, 2)  # Deep ITM (~85% of price, delta ~0.80)
        est_debit = round(price * 0.22, 2)  # ~22% underlying price premium estimate

        return TradeProposal(
            strategy_name=self.name,
            symbol=context.symbol,
            expiration="365DTE",
            dte=365,
            legs=[
                {"side": "BUY", "type": "CALL", "strike": strike, "delta": 0.80, "dte": 365},
            ],
            entry_debit_credit=est_debit,
            max_risk_dollars=est_debit * 100.0,
            max_profit_dollars=None,  # Unlimited upside
            break_even_price=round(strike + est_debit, 2),
            invalidation_price=round(price * 0.90, 2),
            target_price=round(price * 1.25, 2),
            quality_grade="A+" if context.iv_rank <= 25.0 else "A",
        )
