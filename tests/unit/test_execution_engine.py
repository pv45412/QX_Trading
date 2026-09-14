"""Unit tests for QX Real-Time Execution & Order Management System."""

import pytest
from qx.execution import (
    BracketManager,
    BracketParameters,
    ExecutionFill,
    Order,
    OrderRequest,
    OrderRouter,
    OrderSide,
    OrderStatus,
    OrderType,
    compute_order_slippage,
    reconcile_fills,
)


def test_order_submission_and_market_autofill():
    """Verify order router submits market orders and handles simulated fills."""
    router = OrderRouter()
    req = OrderRequest(
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=100.0,
        publication_state="VERIFIED",
        executable=True,
    )
    order = router.submit_order(req, current_market_price=150.0)

    assert order.symbol == "AAPL"
    assert order.status == OrderStatus.FILLED
    assert order.filled_quantity == 100.0
    assert len(order.fills) == 1
    assert order.fills[0].fill_price == 150.0


def test_limit_order_submission_and_manual_fill():
    """Verify limit order placement and execution fill tracking."""
    router = OrderRouter()
    req = OrderRequest(
        symbol="NVDA",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=50.0,
        limit_price=120.0,
        publication_state="VERIFIED",
        executable=True,
    )
    order = router.submit_order(req)
    assert order.status == OrderStatus.SUBMITTED

    fill = router.execute_fill(order.order_id, fill_price=119.50, fill_quantity=50.0)
    assert fill.fill_price == 119.50
    assert order.status == OrderStatus.FILLED


def test_order_cancellation():
    """Verify cancelling open orders."""
    router = OrderRouter()
    req = OrderRequest(
        symbol="MSFT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=20.0,
        limit_price=400.0,
        publication_state="VERIFIED",
        executable=True,
    )
    order = router.submit_order(req)
    canceled = router.cancel_order(order.order_id)
    assert canceled.status == OrderStatus.CANCELED


def test_bracket_manager_triggers():
    """Verify bracket manager evaluates take-profit and stop-loss triggers."""
    manager = BracketManager()
    order = Order(
        symbol="XLK",
        side=OrderSide.BUY,
        order_type=OrderType.BRACKET,
        quantity=100.0,
        status=OrderStatus.FILLED,
        bracket=BracketParameters(take_profit_price=220.0, stop_loss_price=190.0),
    )

    # Test price hitting take profit
    triggers = manager.evaluate_bracket_triggers([order], {"XLK": 222.0})
    assert len(triggers) == 1
    assert triggers[0]["trigger_type"] == "TAKE_PROFIT"
    assert triggers[0]["recommended_action"] == "SELL"

    # Test price hitting stop loss
    triggers_stop = manager.evaluate_bracket_triggers([order], {"XLK": 188.0})
    assert len(triggers_stop) == 1
    assert triggers_stop[0]["trigger_type"] == "STOP_LOSS"


def test_slippage_and_reconciliation():
    """Verify slippage calculation and fill reconciliation math."""
    order = Order(
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100.0,
        limit_price=500.0,
    )
    fill = ExecutionFill(
        order_id=order.order_id,
        symbol="SPY",
        side=OrderSide.BUY,
        filled_quantity=100.0,
        fill_price=501.0,  # 1 point adverse slippage
    )

    slippage_bps = compute_order_slippage(order, fill)
    assert pytest.approx(slippage_bps, rel=1e-3) == 20.0  # (1 / 500) * 10000 = 20 bps

    reconciled = reconcile_fills([fill])
    assert reconciled["total_quantity"] == 100.0
    assert reconciled["weighted_average_price"] == 501.0
