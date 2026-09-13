"""SPX Calendar Strategy Module (Section 13)."""

from typing import Any
from qx.strategies.base import BaseStrategyModule, StrategyContext, TradeProposal


class SPXCalendarModule(BaseStrategyModule):
    @property
    def name(self) -> str:
        return "SPX Calendar Spread"

    def evaluate_compatibility(self, context: StrategyContext) -> float:
        # SPX Calendars favor low directional bias (rangebound/compression) and IV term structure edge
        neutral_fit = 100.0 - abs(context.direction_score - 50.0) * 2.0
        vol_fit = 80.0 if context.iv_rank <= 40.0 else 40.0
        score = (0.6 * neutral_fit) + (0.4 * vol_fit)
        return round(min(100.0, max(0.0, score)), 2)

    def construct_trade(self, context: StrategyContext, chain_data: dict[str, Any]) -> TradeProposal | None:
        price = context.underlying_price
        at_the_money_strike = round(price / 5.0) * 5.0  # Round to nearest $5 strike for SPX

        est_debit = round(price * 0.015, 2)  # ~1.5% of SPX price debit estimate

        return TradeProposal(
            strategy_name=self.name,
            symbol=context.symbol,
            expiration="Front: 7DTE / Back: 30DTE",
            dte=7,
            legs=[
                {"side": "SELL", "type": "CALL", "strike": at_the_money_strike, "dte": 7},
                {"side": "BUY", "type": "CALL", "strike": at_the_money_strike, "dte": 30},
            ],
            entry_debit_credit=est_debit,
            max_risk_dollars=est_debit * 100.0,
            max_profit_dollars=round(est_debit * 1.5 * 100.0, 2),
            break_even_price=round(at_the_money_strike - (est_debit * 0.8), 2),
            invalidation_price=round(at_the_money_strike - (est_debit * 1.2), 2),
            target_price=at_the_money_strike,
            quality_grade="A+" if context.iv_rank <= 30.0 else "A",
        )
