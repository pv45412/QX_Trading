"""Asynchronous pub/sub Event Bus for QX real-time streaming."""

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Callable, Coroutine
from uuid import uuid4
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EventTopic(str, Enum):
    TICKS = "ticks"
    SIGNALS = "signals"
    ORDERS = "orders"
    TELEMETRY = "telemetry"
    SYSTEM = "system"


class StreamMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    topic: EventTopic
    symbol: str | None = None
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    """In-memory thread-safe asynchronous pub/sub event bus."""

    def __init__(self) -> None:
        self._subscribers: dict[EventTopic, set[asyncio.Queue]] = defaultdict(set)
        self._callback_listeners: dict[EventTopic, set[Callable[[StreamMessage], Coroutine[Any, Any, None]]]] = defaultdict(set)

    def subscribe(self, topic: EventTopic) -> asyncio.Queue:
        """Subscribe to an event topic channel returning an async queue."""
        queue: asyncio.Queue[StreamMessage] = asyncio.Queue(maxsize=1000)
        self._subscribers[topic].add(queue)
        return queue

    def unsubscribe(self, topic: EventTopic, queue: asyncio.Queue) -> None:
        """Unsubscribe a queue from a topic channel."""
        if queue in self._subscribers[topic]:
            self._subscribers[topic].remove(queue)

    def add_listener(
        self, topic: EventTopic, callback: Callable[[StreamMessage], Coroutine[Any, Any, None]]
    ) -> None:
        """Add an asynchronous callback listener for a topic channel."""
        self._callback_listeners[topic].add(callback)

    def remove_listener(
        self, topic: EventTopic, callback: Callable[[StreamMessage], Coroutine[Any, Any, None]]
    ) -> None:
        """Remove a callback listener."""
        if callback in self._callback_listeners[topic]:
            self._callback_listeners[topic].remove(callback)

    async def publish(self, topic: EventTopic, payload: dict[str, Any], symbol: str | None = None) -> StreamMessage:
        """Publish a message to a topic channel and dispatch to all subscriber queues and callbacks."""
        message = StreamMessage(topic=topic, symbol=symbol, payload=payload)

        # Dispatch to queue subscribers
        for queue in list(self._subscribers[topic]):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue full for topic %s, dropping oldest message.", topic)
                try:
                    queue.get_nowait()
                    queue.put_nowait(message)
                except Exception:
                    pass

        # Dispatch to async callback listeners
        for listener in list(self._callback_listeners[topic]):
            try:
                await listener(message)
            except Exception as e:
                logger.error("Error in event bus callback listener for topic %s: %s", topic, e)

        return message
