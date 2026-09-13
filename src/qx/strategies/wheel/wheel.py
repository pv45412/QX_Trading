"""Wheel Strategy Module (Cash-Secured Put / Covered Call lifecycle)."""

from typing import Any
from qx.strategies.base import BaseStrategyModule, StrategyContext, TradeProposal


class WheelStrategyModule(BaseStrategyModule):
    @property
    def name(self) -> str:
        return "Wheel Strategy (Cash-Secured Put)"

    def evaluate_compatibility(self, context: StrategyContext) -> float:
        # Wheel favors high IV rank (> 50) and neutral-to-bullish bias (45-75)
        if context.direction_score < 40.0:
            return 0.0

        dir_fit = 100.0 - abs(context.direction_score - 60.0) * 2.0
        vol_fit = context.iv_rank  # Higher fit when IV Rank is elevated (high premium collection)
        score = (0.4 * dir_fit) + (0.6 * vol_fit)
        return round(min(100.0, max(0.0, score)), 2)

    def construct_trade(self, context: StrategyContext, chain_data: dict[str, Any]) -> TradeProposal | None:
        price = context.underlying_price
        put_strike = round(price * 0.95, 2)  # 5% OTM Short Put (30 DTE, delta ~0.30)
        est_credit = round(price * 0.025, 2)  # ~2.5% credit collection

        return TradeProposal(
            strategy_name=self.name,
            symbol=context.symbol,
            expiration="30DTE",
            dte=30,
            legs=[
                {"side": "SELL", "type": "PUT", "strike": put_strike, "dte": 30, "delta": 0.30},
            ],
            entry_debit_credit=-est_credit,  # Credit
            max_risk_dollars=round((put_strike - est_credit) * 100.0, 2),
            max_profit_dollars=round(est_credit * 100.0, 2),
            break_even_price=round(put_strike - est_credit, 2),
            invalidation_price=round(put_strike * 0.90, 2),
            target_price=price,
            quality_grade="A+" if context.iv_rank >= 60.0 else "B",
        )
