"""Smart Order Router for paper and live order placement."""

from datetime import datetime, timezone
import logging
from qx.execution.models import ExecutionFill, Order, OrderRequest, OrderSide, OrderStatus, OrderType

logger = logging.getLogger(__name__)


class OrderRouter:
    """In-memory smart order routing and paper execution engine."""

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}

    def submit_order(self, request: OrderRequest, current_market_price: float | None = None) -> Order:
        """Submit a new order request and attempt immediate simulation fill for MARKET orders."""
        order = Order(
            symbol=request.symbol.upper(),
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            bracket=request.bracket,
            time_in_force=request.time_in_force,
            status=OrderStatus.SUBMITTED,
        )

        # Pre-trade validation check
        if request.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT} and request.limit_price is None:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "Limit price is required for LIMIT and STOP_LIMIT orders."
            self._orders[order.order_id] = order
            return order

        if request.order_type in {OrderType.STOP, OrderType.STOP_LIMIT} and request.stop_price is None:
            order.status = OrderStatus.REJECTED
            order.reject_reason = "Stop price is required for STOP and STOP_LIMIT orders."
            self._orders[order.order_id] = order
            return order

        self._orders[order.order_id] = order

        # Auto-fill MARKET orders if market price is provided
        if request.order_type == OrderType.MARKET and current_market_price is not None and current_market_price > 0:
            self.execute_fill(order.order_id, fill_price=current_market_price, fill_quantity=order.quantity)

        return self._orders[order.order_id]

    def execute_fill(self, order_id: str, fill_price: float, fill_quantity: float) -> ExecutionFill:
        """Execute a fill against an active order."""
        if order_id not in self._orders:
            raise KeyError(f"Order ID {order_id} not found.")

        order = self._orders[order_id]
        if order.status in {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED}:
            raise ValueError(f"Cannot fill order {order_id} with status {order.status}.")

        fill = ExecutionFill(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            filled_quantity=fill_quantity,
            fill_price=fill_price,
            filled_at=datetime.now(timezone.utc),
        )

        order.fills.append(fill)
        order.filled_quantity += fill_quantity
        order.updated_at = datetime.now(timezone.utc)

        if order.filled_quantity >= order.quantity:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIALLY_FILLED

        return fill

    def cancel_order(self, order_id: str) -> Order:
        """Cancel an open or pending order."""
        if order_id not in self._orders:
            raise KeyError(f"Order ID {order_id} not found.")

        order = self._orders[order_id]
        if order.status == OrderStatus.FILLED:
            raise ValueError(f"Cannot cancel order {order_id} because it is already FILLED.")

        order.status = OrderStatus.CANCELED
        order.updated_at = datetime.now(timezone.utc)
        return order

    def get_order(self, order_id: str) -> Order | None:
        """Retrieve an order by ID."""
        return self._orders.get(order_id)

    def list_orders(self, symbol: str | None = None) -> list[Order]:
        """List orders optionally filtered by ticker symbol."""
        if symbol:
            sym_clean = symbol.strip().upper()
            return [o for o in self._orders.values() if o.symbol == sym_clean]
        return list(self._orders.values())
