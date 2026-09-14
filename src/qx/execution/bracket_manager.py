"""Bracket order stop-loss and take-profit trigger engine."""

from typing import Iterable
from qx.execution.models import Order, OrderSide, OrderStatus


class BracketManager:
    """Evaluates active position bracket parameters against current market prices."""

    def evaluate_bracket_triggers(self, orders: Iterable[Order], current_prices: dict[str, float]) -> list[dict]:
        """Check all active bracket orders against latest market prices to identify triggered stops/targets.

        Returns a list of trigger event dictionaries detailing triggered actions.
        """
        triggers = []
        for order in orders:
            if order.status not in {OrderStatus.FILLED, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}:
                continue
            if order.bracket is None:
                continue

            price = current_prices.get(order.symbol.upper())
            if price is None or price <= 0:
                continue

            take_profit = order.bracket.take_profit_price
            stop_loss = order.bracket.stop_loss_price

            if order.side in {OrderSide.BUY, OrderSide.BUY_TO_COVER}:
                # Long position logic
                if price >= take_profit:
                    triggers.append({
                        "order_id": order.order_id,
                        "symbol": order.symbol,
                        "trigger_type": "TAKE_PROFIT",
                        "target_price": take_profit,
                        "current_price": price,
                        "recommended_action": "SELL",
                    })
                elif price <= stop_loss:
                    triggers.append({
                        "order_id": order.order_id,
                        "symbol": order.symbol,
                        "trigger_type": "STOP_LOSS",
                        "target_price": stop_loss,
                        "current_price": price,
                        "recommended_action": "SELL",
                    })
            elif order.side in {OrderSide.SELL, OrderSide.SELL_SHORT}:
                # Short position logic
                if price <= take_profit:
                    triggers.append({
                        "order_id": order.order_id,
                        "symbol": order.symbol,
                        "trigger_type": "TAKE_PROFIT",
                        "target_price": take_profit,
                        "current_price": price,
                        "recommended_action": "BUY_TO_COVER",
                    })
                elif price >= stop_loss:
                    triggers.append({
                        "order_id": order.order_id,
                        "symbol": order.symbol,
                        "trigger_type": "STOP_LOSS",
                        "target_price": stop_loss,
                        "current_price": price,
                        "recommended_action": "BUY_TO_COVER",
                    })

        return triggers
