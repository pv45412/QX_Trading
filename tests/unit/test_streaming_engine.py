"""Unit tests for QX Real-Time WebSocket Streaming & Event Bus Engine."""

import asyncio
import pytest
from qx.streaming import ConnectionManager, EventBus, EventTopic, StreamMessage


@pytest.mark.anyio
async def test_event_bus_publish_and_subscribe():
    """Verify async event bus pub/sub queue dispatch."""
    bus = EventBus()
    queue = bus.subscribe(EventTopic.TICKS)

    msg = await bus.publish(EventTopic.TICKS, payload={"price": 150.25, "volume": 500}, symbol="AAPL")

    assert msg.topic == EventTopic.TICKS
    assert msg.symbol == "AAPL"
    assert msg.payload["price"] == 150.25

    received = await queue.get()
    assert received.message_id == msg.message_id
    assert received.payload["price"] == 150.25


@pytest.mark.anyio
async def test_event_bus_async_callback_listeners():
    """Verify event bus callback listener invocations."""
    bus = EventBus()
    received_messages = []

    async def _on_signal(msg: StreamMessage):
        received_messages.append(msg)

    bus.add_listener(EventTopic.SIGNALS, _on_signal)
    await bus.publish(EventTopic.SIGNALS, payload={"signal": "BULLISH_BREAKOUT"}, symbol="NVDA")

    assert len(received_messages) == 1
    assert received_messages[0].symbol == "NVDA"

    bus.remove_listener(EventTopic.SIGNALS, _on_signal)
    await bus.publish(EventTopic.SIGNALS, payload={"signal": "BEARISH_REVERSAL"}, symbol="NVDA")
    assert len(received_messages) == 1  # Unsubscribed listener should not receive second event


def test_connection_manager_subscriptions():
    """Verify ConnectionManager topic subscription routing."""
    bus = EventBus()
    manager = ConnectionManager(event_bus=bus)

    dummy_socket = object()
    manager.subscriptions[dummy_socket] = set()

    manager.subscribe(dummy_socket, ["ticks", "orders"])
    assert EventTopic.TICKS in manager.subscriptions[dummy_socket]
    assert EventTopic.ORDERS in manager.subscriptions[dummy_socket]

    manager.unsubscribe(dummy_socket, ["ticks"])
    assert EventTopic.TICKS not in manager.subscriptions[dummy_socket]
    assert EventTopic.ORDERS in manager.subscriptions[dummy_socket]
