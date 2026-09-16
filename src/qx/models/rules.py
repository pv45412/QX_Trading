"""Phase 1: Deterministic Rules Engine Data Models & Enums.

Strictly separates Publication State from Signal State, incorporates Rule Severity,
and expands Market Regime dimensions.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# --- SEPARATE PUBLICATION STATE FROM SIGNAL STATE ---
class PublicationState(str, Enum):
    VERIFIED = "VERIFIED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    SIMULATED = "SIMULATED"
    BLOCKED = "BLOCKED"


class SignalState(str, Enum):
    NO_SETUP = "NO_SETUP"
    WATCH = "WATCH"
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    EXECUTABLE = "EXECUTABLE"
    BLOCKED = "BLOCKED"  # Absorbing result caused by failed hard gate in evaluation cycle


class RuleSeverity(str, Enum):
    INFO = "INFO"    # Diagnostic observation only
    SOFT = "SOFT"    # Contributes to setup quality / ranking score
    HARD = "HARD"    # Hard gate failure immediately vetoes eligibility


class CalibrationStatus(str, Enum):
    RESEARCH = "RESEARCH"
    UNVALIDATED = "UNVALIDATED"
    CALIBRATING = "CALIBRATING"
    VALIDATED = "VALIDATED"


class DeltaProvenance(str, Enum):
    ACTUAL_TRADE_AGGRESSOR = "ACTUAL_TRADE_AGGRESSOR"
    ESTIMATED_BID_ASK = "ESTIMATED_BID_ASK"
    BAR_DERIVED = "BAR_DERIVED"
    UNAVAILABLE = "UNAVAILABLE"


class GammaProvenance(str, Enum):
    PROVIDER_ESTIMATED_GEX = "PROVIDER_ESTIMATED_GEX"
    MODEL_ESTIMATED_GEX = "MODEL_ESTIMATED_GEX"
    DERIVED_FROM_OPEN_INTEREST = "DERIVED_FROM_OPEN_INTEREST"
    UNAVAILABLE = "UNAVAILABLE"


class FreshnessStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceCoverageStatus(str, Enum):
    INSUFFICIENT = "INSUFFICIENT"
    PARTIAL = "PARTIAL"
    ADEQUATE = "ADEQUATE"
    STRONG = "STRONG"
    COMPLETE = "COMPLETE"


# --- EXPANDED MARKET REGIME DIMENSIONS ---
class TrendRegime(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"


class VolatilityRegime(str, Enum):
    COMPRESSED = "COMPRESSED"
    NORMAL = "NORMAL"
    EXPANDING = "EXPANDING"


class GammaRegime(str, Enum):
    POSITIVE_GAMMA = "POSITIVE_GAMMA"
    NEGATIVE_GAMMA = "NEGATIVE_GAMMA"
    UNKNOWN = "UNKNOWN"


class SessionRegime(str, Enum):
    OPENING = "OPENING"
    TREND_SESSION = "TREND_SESSION"
    BALANCED = "BALANCED"
    LATE_SESSION = "LATE_SESSION"


class MarketRegimeModel(BaseModel):
    trend: TrendRegime
    volatility: VolatilityRegime
    gamma: GammaRegime
    session: SessionRegime
    trend_evidence: Dict[str, Any] = Field(default_factory=dict)
    volatility_evidence: Dict[str, Any] = Field(default_factory=dict)
    gamma_evidence: Dict[str, Any] = Field(default_factory=dict)
    session_evidence: Dict[str, Any] = Field(default_factory=dict)
    regime_generated_at: str = ""
    data_as_of: str = ""
    config_version: str = "research_v1"
    engine_version: str = "v3.1.0"



# --- GRANULAR RULE RESULT ---
class RuleResult(BaseModel):
    rule_id: str
    rule_version: str = "1.0"
    category: str
    required_value: Any
    observed_value: Any
    passed: bool
    severity: RuleSeverity = RuleSeverity.HARD
    hard_gate: bool = True
    weight: Optional[float] = None
    contribution: Optional[float] = None
    data_source: DeltaProvenance = DeltaProvenance.BAR_DERIVED
    event_timestamp: str = ""
    knowledge_timestamp: str = ""
    detail: str = ""


# --- DETERMINISTIC SIGNAL RESULT ---
class DeterministicSignalResult(BaseModel):
    signal_id: str
    symbol: str
    publication_state: PublicationState
    data_as_of: str
    generated_at: str

    market_regime: MarketRegimeModel
    direction: str  # "BULLISH", "BEARISH", "NEUTRAL"
    direction_score: float = Field(ge=-100.0, le=100.0)

    playbook_id: str
    playbook_version: str = "1.0"

    setup_quality: float = Field(ge=0.0, le=100.0)
    participation_score: float = Field(ge=0.0, le=100.0)
    market_alignment_score: float = Field(ge=0.0, le=100.0)
    tradeability_score: float = Field(ge=0.0, le=100.0)

    signal_state: SignalState

    direction_evidence_coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    participation_evidence_coverage: float = Field(default=1.0, ge=0.0, le=1.0)

    trigger_price: Optional[float] = None
    invalidation_price: Optional[float] = None
    target_levels: List[float] = Field(default_factory=list)
    risk_reward: float = 0.0

    calibration_status: CalibrationStatus = CalibrationStatus.RESEARCH
    delta_provenance: DeltaProvenance = DeltaProvenance.BAR_DERIVED

    evidence_ladder: List[RuleResult] = Field(default_factory=list)

    config_version: str = "research_v1"
    engine_version: str = "v3.1.0"

    event_timestamp: str = ""
    knowledge_timestamp: str = ""

    from pydantic import model_validator

    @model_validator(mode="after")
    def validate_publication_signal_invariant(self):
        if self.signal_state == SignalState.EXECUTABLE and self.publication_state != PublicationState.VERIFIED:
            raise ValueError(
                f"Hard invariant violation: signal_state cannot be EXECUTABLE when publication_state is '{self.publication_state}'. "
                "EXECUTABLE requires publication_state == VERIFIED."
            )
        return self
