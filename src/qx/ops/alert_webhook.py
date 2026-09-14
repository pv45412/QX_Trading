"""External alert webhook dispatcher."""

from datetime import datetime, timezone
import logging
from typing import Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AlertPayload(BaseModel):
    level: str  # "INFO", "WARNING", "CRITICAL"
    source: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AlertDispatcher:
    """Dispatches operational and trade execution alerts to external webhooks."""

    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = webhook_url
        self.history: list[AlertPayload] = []

    def dispatch_alert(self, level: str, source: str, message: str, metadata: dict[str, Any] | None = None) -> AlertPayload:
        """Create and log an alert payload."""
        alert = AlertPayload(
            level=level.upper(),
            source=source,
            message=message,
            metadata=metadata or {},
        )
        self.history.append(alert)

        if level.upper() == "CRITICAL":
            logger.critical("CRITICAL ALERT [%s]: %s", source, message)
        elif level.upper() == "WARNING":
            logger.warning("WARNING ALERT [%s]: %s", source, message)
        else:
            logger.info("INFO ALERT [%s]: %s", source, message)

        return alert

    def get_history(self, limit: int = 50) -> list[AlertPayload]:
        """Retrieve recent alert history."""
        return self.history[-limit:]
