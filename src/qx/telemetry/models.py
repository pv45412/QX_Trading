"""Pydantic models for QX Telemetry & Signal Audit Logging Service."""

from datetime import datetime, timezone
from typing import Optional
import uuid
from pydantic import BaseModel, Field


class SignalTelemetryRecord(BaseModel):
    """Structured telemetry record capturing signal metrics, scores, and decision parameters."""
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    symbol: str
    underlying_price: float
    market_regime: str = "NEUTRAL"
    direction_score: float
    volatility_score: float
    qx_score: float
    recommended_strategy: str
    scoring_version: str = "1.0.0"
    config_version: str = "1.0.0"
    max_risk_dollars: float
    quality_grade: str = "B"
    final_outcome: Optional[str] = None
    realized_pnl: Optional[float] = None
