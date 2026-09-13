"""Bull Call Debit Spread Strategy Module."""

from typing import Any
from qx.strategies.base import BaseStrategyModule, StrategyContext, TradeProposal


class BullCallSpreadModule(BaseStrategyModule):
    @property
    def name(self) -> str:
        return "Bull Call Debit Spread"

    def evaluate_compatibility(self, context: StrategyContext) -> float:
        # High score when directional score > 60 and volatility score <= 60 (cheap/fair IV)
        if context.direction_score < 50.0:
            return 0.0

        dir_fit = (context.direction_score - 50.0) * 2.0  # 0 to 100
        vol_fit = max(0.0, 100.0 - context.iv_rank)  # Higher fit when IV Rank is low (cheap options)
        score = (0.7 * dir_fit) + (0.3 * vol_fit)
        return round(min(100.0, max(0.0, score)), 2)

    def construct_trade(self, context: StrategyContext, chain_data: dict[str, Any]) -> TradeProposal | None:
        price = context.underlying_price
        width = round(price * 0.05, 2)  # 5% spread width default
        long_strike = round(price, 2)
        short_strike = round(price + width, 2)

        est_debit = round(width * 0.40, 2)  # ~40% width debit estimate
        max_profit = round(width - est_debit, 2)

        return TradeProposal(
            strategy_name=self.name,
            symbol=context.symbol,
            expiration="30DTE",
            dte=30,
            legs=[
                {"side": "BUY", "type": "CALL", "strike": long_strike},
                {"side": "SELL", "type": "CALL", "strike": short_strike},
            ],
            entry_debit_credit=est_debit,
            max_risk_dollars=est_debit * 100.0,
            max_profit_dollars=max_profit * 100.0,
            break_even_price=round(long_strike + est_debit, 2),
            invalidation_price=round(price * 0.97, 2),
            target_price=short_strike,
            quality_grade="A" if context.direction_score >= 75.0 else "B",
        )
