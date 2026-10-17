"""MD2 Market Driver Models and Data Contract.

Defines the deterministic backend-owned Market Driver schema, evidence tokens,
archetypes, coverage audit, and presentation structures in compliance with
the human-approved MD1 Option B specification.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MarketDriverStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    UNAVAILABLE = "UNAVAILABLE"
    BLOCKED = "BLOCKED"


class DriverDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"


class DriverStrength(str, Enum):
    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"


class PersistenceState(str, Enum):
    STRENGTHENING = "STRENGTHENING"
    STABLE = "STABLE"
    WEAKENING = "WEAKENING"
    NEW = "NEW"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceClassification(str, Enum):
    CONFIRMING = "CONFIRMING"
    CONFLICTING = "CONFLICTING"
    NEUTRAL = "NEUTRAL"


class DriverArchetype(str, Enum):
    INDEX_RISK_ON = "INDEX_RISK_ON"
    INDEX_RISK_OFF = "INDEX_RISK_OFF"
    SECTOR_LEADERSHIP = "SECTOR_LEADERSHIP"
    SECTOR_LAG = "SECTOR_LAG"
    GAMMA_PINNING = "GAMMA_PINNING"
    GAMMA_SQUEEZE = "GAMMA_SQUEEZE"
    DELTA_AGGRESSION = "DELTA_AGGRESSION"
    LIQUIDITY_ABSORPTION = "LIQUIDITY_ABSORPTION"
    VWAP_MEAN_REVERSION = "VWAP_MEAN_REVERSION"
    MACRO_CATALYST = "MACRO_CATALYST"
    IDIOSYNCRATIC_FLOW = "IDIOSYNCRATIC_FLOW"


ARCHETYPE_LABELS: Dict[DriverArchetype, str] = {
    DriverArchetype.INDEX_RISK_ON: "Broad risk-on / index buying",
    DriverArchetype.INDEX_RISK_OFF: "Broad risk-off / index selling",
    DriverArchetype.SECTOR_LEADERSHIP: "Sector outperformance / rotation",
    DriverArchetype.SECTOR_LAG: "Sector weakness / rotation outflow",
    DriverArchetype.GAMMA_PINNING: "Dealer gamma pinning / compression",
    DriverArchetype.GAMMA_SQUEEZE: "Negative gamma acceleration / squeeze",
    DriverArchetype.DELTA_AGGRESSION: "Aggressive order flow imbalance",
    DriverArchetype.LIQUIDITY_ABSORPTION: "Passive liquidity absorption",
    DriverArchetype.VWAP_MEAN_REVERSION: "Mean reversion to volume-weighted price",
    DriverArchetype.MACRO_CATALYST: "Scheduled macroeconomic event / news",
    DriverArchetype.IDIOSYNCRATIC_FLOW: "Uncorrelated symbol-specific flow",
}


class DriverPersistence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: PersistenceState = PersistenceState.UNAVAILABLE
    duration_seconds: int = 0
    started_at: Optional[datetime] = None
    bars_active: int = 0
    minutes_active: Optional[float] = None
    previous_primary_driver: Optional[str] = None
    candidate_margin: Optional[float] = None


class PrimaryDriver(BaseModel):
    model_config = ConfigDict(extra="forbid")

    driver_id: str
    label: str
    direction: DriverDirection
    strength: DriverStrength
    magnitude: float = 0.0
    persistence: DriverPersistence = Field(default_factory=DriverPersistence)


class SecondaryDriver(BaseModel):
    model_config = ConfigDict(extra="forbid")

    driver_id: str
    label: str
    direction: DriverDirection
    strength: DriverStrength
    magnitude: float = 0.0


class EvidenceToken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    label: str
    source_stage: str
    event_timestamp: Optional[datetime] = None
    knowledge_timestamp: Optional[datetime] = None
    source: str
    raw_value: Optional[float] = None
    normalized_score: float = 0.0
    reliability: float = 1.0
    freshness: str = "FRESH"
    provenance: str = "CANONICAL"
    classification: EvidenceClassification = EvidenceClassification.NEUTRAL


class CoverageAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    observed_sources: int = 0
    required_sources: int = 5
    missing_sources: List[str] = Field(default_factory=list)
    source_details: Dict[str, Any] = Field(default_factory=dict)


class MarketDriverResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: MarketDriverStatus
    primary_driver: Optional[PrimaryDriver] = None
    secondary_drivers: List[SecondaryDriver] = Field(default_factory=list)
    confirming_evidence: List[EvidenceToken] = Field(default_factory=list)
    conflicting_evidence: List[EvidenceToken] = Field(default_factory=list)
    coverage: CoverageAudit
    data_as_of: Optional[datetime] = None
    knowledge_timestamp: Optional[datetime] = None
    engine_version: str = "market_driver_v1.0.0"
    reason_codes: List[str] = Field(default_factory=list)
    input_fingerprint: Optional[str] = None

    def to_presentation_dict(self) -> Dict[str, Any]:
        """Converts result to the standard JSON presentation contract."""
        return {
            "status": self.status.value,
            "primary_driver": (
                {
                    "driver_id": self.primary_driver.driver_id,
                    "label": self.primary_driver.label,
                    "direction": self.primary_driver.direction.value,
                    "strength": self.primary_driver.strength.value,
                    "magnitude": round(self.primary_driver.magnitude, 2),
                    "persistence": {
                        "state": self.primary_driver.persistence.state.value,
                        "duration_seconds": self.primary_driver.persistence.duration_seconds,
                        "started_at": (
                            self.primary_driver.persistence.started_at.isoformat()
                            if self.primary_driver.persistence.started_at
                            else None
                        ),
                        "bars_active": self.primary_driver.persistence.bars_active,
                        "minutes_active": self.primary_driver.persistence.minutes_active,
                        "previous_primary_driver": self.primary_driver.persistence.previous_primary_driver,
                        "candidate_margin": self.primary_driver.persistence.candidate_margin,
                    },
                }
                if self.primary_driver
                else None
            ),
            "secondary_drivers": [
                {
                    "driver_id": sd.driver_id,
                    "label": sd.label,
                    "direction": sd.direction.value,
                    "strength": sd.strength.value,
                    "magnitude": round(sd.magnitude, 2),
                }
                for sd in self.secondary_drivers
            ],
            "confirming_evidence": [
                {
                    "evidence_id": ev.evidence_id,
                    "label": ev.label,
                    "source_stage": ev.source_stage,
                    "event_timestamp": ev.event_timestamp.isoformat() if ev.event_timestamp else None,
                    "knowledge_timestamp": ev.knowledge_timestamp.isoformat() if ev.knowledge_timestamp else None,
                    "source": ev.source,
                    "raw_value": ev.raw_value,
                    "normalized_score": ev.normalized_score,
                    "reliability": ev.reliability,
                    "freshness": ev.freshness,
                    "provenance": ev.provenance,
                    "classification": ev.classification.value,
                }
                for ev in self.confirming_evidence
            ],
            "conflicting_evidence": [
                {
                    "evidence_id": ev.evidence_id,
                    "label": ev.label,
                    "source_stage": ev.source_stage,
                    "event_timestamp": ev.event_timestamp.isoformat() if ev.event_timestamp else None,
                    "knowledge_timestamp": ev.knowledge_timestamp.isoformat() if ev.knowledge_timestamp else None,
                    "source": ev.source,
                    "raw_value": ev.raw_value,
                    "normalized_score": ev.normalized_score,
                    "reliability": ev.reliability,
                    "freshness": ev.freshness,
                    "provenance": ev.provenance,
                    "classification": ev.classification.value,
                }
                for ev in self.conflicting_evidence
            ],
            "coverage": {
                "status": self.coverage.status,
                "observed_sources": self.coverage.observed_sources,
                "required_sources": self.coverage.required_sources,
                "missing_sources": list(self.coverage.missing_sources),
            },
            "data_as_of": self.data_as_of.isoformat() if self.data_as_of else None,
            "knowledge_timestamp": self.knowledge_timestamp.isoformat() if self.knowledge_timestamp else None,
            "engine_version": self.engine_version,
            "reason_codes": list(self.reason_codes),
            "input_fingerprint": self.input_fingerprint,
        }
