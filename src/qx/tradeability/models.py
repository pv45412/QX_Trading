"""Phase 8 underlying tradeability models."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from qx.models.rules import DeltaProvenance, PublicationState, SignalState
from qx.triggers.models import TriggeredSetupResult


class TradeabilityState(str, Enum):
    TRADEABLE = "TRADEABLE"
    NOT_TRADEABLE = "NOT_TRADEABLE"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"


class LiquidityApplicability(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class TradeabilityReasonCode(str, Enum):
    TRADEABLE_ALL_GATES_PASS = "TRADEABLE_ALL_GATES_PASS"
    BLOCKED_PUBLICATION_STATE = "BLOCKED_PUBLICATION_STATE"
    INVALID_TRIGGER_STATE = "INVALID_TRIGGER_STATE"
    TRIGGER_SOURCE_INVALID = "TRIGGER_SOURCE_INVALID"
    STRUCTURAL_SOURCE_INVALID = "STRUCTURAL_SOURCE_INVALID"
    TRIGGERED_SETUP_INVALIDATED = "TRIGGERED_SETUP_INVALIDATED"
    EVIDENCE_NOT_COMPLETE = "EVIDENCE_NOT_COMPLETE"
    SETUP_EXPIRED = "SETUP_EXPIRED"
    STALE_MARKET_DATA = "STALE_MARKET_DATA"
    INSUFFICIENT_PARTICIPATION = "INSUFFICIENT_PARTICIPATION"
    INSUFFICIENT_PARTICIPATION_EVIDENCE = "INSUFFICIENT_PARTICIPATION_EVIDENCE"
    EXCESSIVE_EXTENSION = "EXCESSIVE_EXTENSION"
    GAP_TOO_LARGE = "GAP_TOO_LARGE"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    INSUFFICIENT_RISK_REWARD = "INSUFFICIENT_RISK_REWARD"
    INVALID_RISK_GEOMETRY = "INVALID_RISK_GEOMETRY"
    NO_VALID_STRUCTURAL_TARGET = "NO_VALID_STRUCTURAL_TARGET"
    DELTA_CONFLICT = "DELTA_CONFLICT"
    LIQUIDITY_UNKNOWN = "LIQUIDITY_UNKNOWN"
    RVOL_TIMEZONE_MISMATCH = "RVOL_TIMEZONE_MISMATCH"
    RVOL_SESSION_MISMATCH = "RVOL_SESSION_MISMATCH"
    RVOL_DATA_LEAKAGE = "RVOL_DATA_LEAKAGE"
    INSUFFICIENT_RVOL_HISTORY = "INSUFFICIENT_RVOL_HISTORY"


class RVOLBaseline(BaseModel):
    """Precomputed volume baseline for one exact intraday slot."""

    symbol: str
    timeframe: str
    time_slot: str
    slot_mean_volume: float
    slot_median_volume: float
    slot_std: float
    baseline_sessions_used: int
    baseline_computed_at: str
    lookback_sessions: int = 20
    historical_slot_volumes: List[float] = Field(default_factory=list)
    slot_timezone: str = "America/New_York"
    session_type: str = "RTH"
    baseline_session_dates: List[str] = Field(default_factory=list)


class RVOLResult(BaseModel):
    current_volume: float
    slot_mean_volume: float
    slot_median_volume: float
    slot_std: float
    rvol_mean_ratio: float
    rvol_median_ratio: float
    volume_percentile: float
    baseline_sessions_used: int
    time_slot: str
    normalized: bool
    slot_timezone: str = "America/New_York"
    session_type: str = "RTH"


class TradeabilityMarketEvidence(BaseModel):
    """Deterministic market evidence available after trigger confirmation."""

    current_price: float
    atr: float
    evaluation_timestamp: str
    data_as_of: str
    evaluation_session_date: str = ""
    session_type: str = "RTH"
    slot_timezone: str = "America/New_York"
    liquidity_applicability: LiquidityApplicability = LiquidityApplicability.AVAILABLE
    quote_age_seconds: float = 0.0
    completed_bar_evidence_available: bool = True
    bid: Optional[float] = None
    ask: Optional[float] = None
    current_volume: float = 0.0
    current_time_slot: Optional[str] = None
    rvol_baseline: Optional[RVOLBaseline] = None
    rvol_age_seconds: Optional[float] = None
    delta_value: Optional[float] = None
    delta_level: Optional[float] = None
    delta_directional_alignment: Optional[bool] = None
    delta_change: Optional[float] = None
    delta_slope: Optional[float] = None
    delta_level: Optional[float] = None
    delta_directional_alignment: Optional[bool] = None
    delta_change: Optional[float] = None
    delta_slope: Optional[float] = None
    delta_provenance: DeltaProvenance = DeltaProvenance.UNAVAILABLE
    delta_age_seconds: Optional[float] = None
    structural_target_candidates: List[float] = Field(default_factory=list)
    bars_since_trigger: int = 0
    seconds_since_trigger: float = 0.0


class TradeabilityContext(BaseModel):
    """Normalized Phase 8 context derived from Phase 7 and current evidence."""

    triggered_setup_id: str
    playbook_id: str
    symbol: str
    timeframe: str
    direction: str
    source_state: SignalState = SignalState.TRIGGERED
    trigger_price: float
    invalidation_price: float
    trigger_source_still_valid: bool = True
    structure_source_still_valid: bool = True
    current_price: float
    quote_age_seconds: float = 0.0
    completed_bar_evidence_available: bool = True
    liquidity_applicability: LiquidityApplicability = LiquidityApplicability.AVAILABLE
    bid: Optional[float] = None
    ask: Optional[float] = None
    atr: float
    current_volume: float = 0.0
    current_time_slot: Optional[str] = None
    rvol_baseline: Optional[RVOLBaseline] = None
    rvol_age_seconds: Optional[float] = None
    delta_value: Optional[float] = None
    delta_level: Optional[float] = None
    delta_directional_alignment: Optional[bool] = None
    delta_change: Optional[float] = None
    delta_slope: Optional[float] = None
    delta_provenance: DeltaProvenance = DeltaProvenance.UNAVAILABLE
    delta_age_seconds: Optional[float] = None
    structural_target_candidates: List[float] = Field(default_factory=list)
    gap_beyond_trigger: bool = False
    gap_distance_atr: float = 0.0
    bars_since_trigger: int = 0
    seconds_since_trigger: float = 0.0
    triggered_at: str
    trigger_confirmed_at: str = ""
    evaluation_timestamp: str
    data_as_of: str = ""
    evaluation_session_date: str = ""
    session_type: str = "RTH"
    slot_timezone: str = "America/New_York"
    publication_state: PublicationState = PublicationState.VERIFIED

    @classmethod
    def from_triggered_setup(
        cls,
        setup: TriggeredSetupResult,
        evidence: TradeabilityMarketEvidence,
    ) -> "TradeabilityContext":
        trigger_event = setup.trigger_event
        return cls(
            triggered_setup_id=setup.playbook_evaluation_id,
            playbook_id=setup.playbook_id,
            symbol=setup.symbol,
            timeframe=setup.timeframe,
            direction=setup.direction,
            source_state=setup.state,
            trigger_price=setup.trigger_price,
            invalidation_price=setup.invalidation_price,
            trigger_source_still_valid=setup.trigger_source_valid,
            structure_source_still_valid=setup.structure_valid,
            current_price=evidence.current_price,
            quote_age_seconds=evidence.quote_age_seconds,
            completed_bar_evidence_available=evidence.completed_bar_evidence_available,
            liquidity_applicability=evidence.liquidity_applicability,
            bid=evidence.bid,
            ask=evidence.ask,
            atr=evidence.atr,
            current_volume=evidence.current_volume,
            current_time_slot=evidence.current_time_slot,
            rvol_baseline=evidence.rvol_baseline,
            rvol_age_seconds=evidence.rvol_age_seconds,
            delta_value=evidence.delta_value,
            delta_level=evidence.delta_level,
            delta_directional_alignment=evidence.delta_directional_alignment,
            delta_change=evidence.delta_change,
            delta_slope=evidence.delta_slope,
            delta_provenance=evidence.delta_provenance,
            delta_age_seconds=evidence.delta_age_seconds,
            structural_target_candidates=evidence.structural_target_candidates,
            gap_beyond_trigger=bool(trigger_event and trigger_event.gap_beyond_trigger),
            gap_distance_atr=trigger_event.gap_distance_atr if trigger_event else 0.0,
            bars_since_trigger=evidence.bars_since_trigger,
            seconds_since_trigger=evidence.seconds_since_trigger,
            triggered_at=setup.trigger_event_timestamp,
            trigger_confirmed_at=setup.trigger_confirmed_at,
            evaluation_timestamp=evidence.evaluation_timestamp,
            data_as_of=evidence.data_as_of,
            evaluation_session_date=evidence.evaluation_session_date,
            session_type=evidence.session_type,
            slot_timezone=evidence.slot_timezone,
            publication_state=setup.publication_state,
        )


class TradeabilityResult(BaseModel):
    """Phase 8 result; never an order or execution authorization."""

    model_config = ConfigDict(extra="forbid")

    tradeability_id: str
    triggered_setup_id: str
    playbook_id: str
    symbol: str
    timeframe: str
    direction: str
    state: TradeabilityState
    publication_state: PublicationState
    trigger_price: float
    observed_underlying_price: float
    observed_entry_reference_price: Optional[float] = None
    invalidation_price: float
    target_candidates: List[float] = Field(default_factory=list)
    participation_score: float = 0.0
    participation_evidence_coverage: float = 0.0
    rvol_normalized: Optional[float] = None
    rvol_percentile: Optional[float] = None
    delta_score: float = 0.0
    delta_level: Optional[float] = None
    delta_directional_alignment: Optional[bool] = None
    delta_change: Optional[float] = None
    delta_slope: Optional[float] = None
    delta_provenance: str = "UNAVAILABLE"
    delta_reliability: float = 0.0
    extension_atr: float = 0.0
    liquidity_applicability: LiquidityApplicability = LiquidityApplicability.AVAILABLE
    spread_absolute: Optional[float] = None
    spread_pct: Optional[float] = None
    liquidity_status: str = "UNKNOWN"
    risk_reward_to_target1: Optional[float] = None
    risk_reward_to_best_structural_target: Optional[float] = None
    gap_beyond_trigger: bool = False
    gap_distance_atr: float = 0.0
    bars_since_trigger: int = 0
    seconds_since_trigger: float = 0.0
    triggered_at: str = ""
    tradeability_evaluated_at: str = ""
    evaluated_at: str = ""
    data_as_of: str = ""
    reason_codes: List[str] = Field(default_factory=list)
    evidence_ladder: Dict[str, Any] = Field(default_factory=dict)
    config_version: str = "research_v1"
    engine_version: str = "v8.1.0"
    trade_state: str = "NONE - OPTIONS EXPRESSION NOT YET EVALUATED"

    @model_validator(mode="after")
    def validate_phase8_invariants(self) -> "TradeabilityResult":
        if self.trade_state != "NONE - OPTIONS EXPRESSION NOT YET EVALUATED":
            raise ValueError(
                "Phase 8 Invariant Violation: trade_state must remain "
                "'NONE - OPTIONS EXPRESSION NOT YET EVALUATED'."
            )
        if self.observed_entry_reference_price is None:
            self.observed_entry_reference_price = self.observed_underlying_price
        if self.observed_entry_reference_price != self.observed_underlying_price:
            raise ValueError("Observed entry reference must equal the evaluated underlying price.")
        if not self.evaluated_at:
            self.evaluated_at = self.tradeability_evaluated_at
        return self
