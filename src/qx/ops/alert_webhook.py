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

    def dispatch_gex_flip_alert(self, symbol: str, spot_price: float, gamma_flip_level: float, regime: str) -> AlertPayload:
        """Dispatch alert when price crosses dealer gamma flip boundary."""
        level = "WARNING" if spot_price < gamma_flip_level else "INFO"
        msg = f"{symbol} (${spot_price:.2f}) crossed Dealer Gamma Flip level (${gamma_flip_level:.2f}). Current Regime: {regime}"
        return self.dispatch_alert(level=level, source="GEX_FLIP_ENGINE", message=msg, metadata={"symbol": symbol, "spot": spot_price, "flip": gamma_flip_level})

    def dispatch_orb_breakout_alert(self, symbol: str, spot_price: float, orb_high: float, orb_low: float, direction: str) -> AlertPayload:
        """Dispatch alert on 15m Opening Range Breakout."""
        msg = f"{symbol} 15m ORB {direction} Trigger! Price: ${spot_price:.2f} (ORB High: ${orb_high:.2f}, ORB Low: ${orb_low:.2f})"
        return self.dispatch_alert(level="INFO", source="ORB_BREAKOUT_ENGINE", message=msg, metadata={"symbol": symbol, "spot": spot_price, "direction": direction})
