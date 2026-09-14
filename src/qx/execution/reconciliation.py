"""Execution fill reconciliation and slippage audit logging."""

from typing import Iterable
from qx.execution.models import ExecutionFill, Order, OrderSide


def compute_order_slippage(order: Order, fill: ExecutionFill) -> float:
    """Calculate slippage in basis points between target limit/benchmark price and actual fill price."""
    benchmark = order.limit_price if order.limit_price is not None else fill.fill_price
    if benchmark <= 0:
        return 0.0

    if order.side in {OrderSide.BUY, OrderSide.BUY_TO_COVER}:
        # Higher fill price = adverse slippage
        diff = fill.fill_price - benchmark
    else:
        # Lower fill price = adverse slippage
        diff = benchmark - fill.fill_price

    return (diff / benchmark) * 10_000.0


def reconcile_fills(fills: Iterable[ExecutionFill]) -> dict:
    """Aggregate total filled volume, average execution price, and total commissions across fills."""
    fills_list = list(fills)
    if not fills_list:
        return {
            "total_quantity": 0.0,
            "weighted_average_price": 0.0,
            "total_commission": 0.0,
            "fill_count": 0,
        }

    total_qty = sum(f.filled_quantity for f in fills_list)
    weighted_sum = sum(f.fill_price * f.filled_quantity for f in fills_list)
    total_commission = sum(f.commission for f in fills_list)

    return {
        "total_quantity": total_qty,
        "weighted_average_price": weighted_sum / total_qty if total_qty > 0 else 0.0,
        "total_commission": total_commission,
        "fill_count": len(fills_list),
    }
