"""FastAPI WebSocket Connection Manager and Channel Router."""

import asyncio
import json
import logging
from typing import Any
from fastapi import WebSocket, WebSocketDisconnect
from qx.streaming.event_bus import EventBus, EventTopic, StreamMessage

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections, subscription topics, and message broadcasting."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.active_connections: list[WebSocket] = []
        self.subscriptions: dict[WebSocket, set[EventTopic]] = {}
        self.event_bus = event_bus or EventBus()
        self._setup_event_listeners()

    def _setup_event_listeners(self) -> None:
        for topic in EventTopic:
            self.event_bus.add_listener(topic, self._broadcast_event_to_websocket)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept connection and initialize default topic subscriptions."""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.subscriptions[websocket] = {EventTopic.SYSTEM, EventTopic.TICKS, EventTopic.SIGNALS}

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove connection on disconnect."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self.subscriptions.pop(websocket, None)

    def subscribe(self, websocket: WebSocket, topics: list[str]) -> None:
        """Subscribe a connection to specific topic channels."""
        if websocket not in self.subscriptions:
            self.subscriptions[websocket] = set()

        for t in topics:
            try:
                topic_enum = EventTopic(t.lower())
                self.subscriptions[websocket].add(topic_enum)
            except ValueError:
                logger.warning("Invalid topic subscription requested: %s", t)

    def unsubscribe(self, websocket: WebSocket, topics: list[str]) -> None:
        """Unsubscribe a connection from topic channels."""
        if websocket in self.subscriptions:
            for t in topics:
                try:
                    topic_enum = EventTopic(t.lower())
                    self.subscriptions[websocket].discard(topic_enum)
                except ValueError:
                    pass

    async def send_personal_message(self, message: dict[str, Any], websocket: WebSocket) -> None:
        """Send a JSON payload to a specific client connection."""
        await websocket.send_text(json.dumps(message))

    async def _broadcast_event_to_websocket(self, message: StreamMessage) -> None:
        """Internal callback to broadcast EventBus messages to subscribed WebSockets."""
        payload_str = message.model_dump_json()
        disconnected = []

        for connection in self.active_connections:
            subscribed_topics = self.subscriptions.get(connection, set())
            if message.topic in subscribed_topics:
                try:
                    await connection.send_text(payload_str)
                except Exception:
                    disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)
