"""Phase 8: Tradeability Engine — Models.

Answers: IS THIS TRIGGERED SETUP ACTUALLY TRADEABLE?

A valid TRIGGERED setup is necessary but not sufficient for a trade.
Phase 8 evaluates underlying tradeability only.

Prohibited outputs:
  - SignalState.EXECUTABLE  (Phase 11)
  - Options contract fields (Phase 9)
  - Portfolio/account risk  (Phase 10)
"""

import math
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

from qx.models.rules import DeltaProvenance, PublicationState


# ---------------------------------------------------------------------------
# TradeabilityState — distinct from SignalState
# ---------------------------------------------------------------------------

class TradeabilityState(str, Enum):
    TRADEABLE = "TRADEABLE"
    NOT_TRADEABLE = "NOT_TRADEABLE"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"


class TradeabilityReasonCode(str, Enum):
    TRADEABLE_ALL_GATES_PASS = "TRADEABLE_ALL_GATES_PASS"
    BLOCKED_PUBLICATION_STATE = "BLOCKED_PUBLICATION_STATE"
    TRIGGER_SOURCE_INVALID = "TRIGGER_SOURCE_INVALID"
    TRIGGERED_SETUP_INVALIDATED = "TRIGGERED_SETUP_INVALIDATED"
    SETUP_EXPIRED = "SETUP_EXPIRED"
    STALE_MARKET_DATA = "STALE_MARKET_DATA"
    INSUFFICIENT_PARTICIPATION = "INSUFFICIENT_PARTICIPATION"
    INSUFFICIENT_PARTICIPATION_EVIDENCE = "INSUFFICIENT_PARTICIPATION_EVIDENCE"
    EXCESSIVE_EXTENSION = "EXCESSIVE_EXTENSION"
    GAP_TOO_LARGE = "GAP_TOO_LARGE"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    INSUFFICIENT_RISK_REWARD = "INSUFFICIENT_RISK_REWARD"
    NO_VALID_STRUCTURAL_TARGET = "NO_VALID_STRUCTURAL_TARGET"
    DELTA_CONFLICT = "DELTA_CONFLICT"
    LIQUIDITY_UNKNOWN = "LIQUIDITY_UNKNOWN"


# ---------------------------------------------------------------------------
# RVOL Models
# ---------------------------------------------------------------------------

class RVOLBaseline(BaseModel):
    """Pre-computed same-slot volume baseline.

    Cached by (symbol, timeframe, time_slot, lookback_window).
    Must be computed from prior completed sessions only — no lookahead.
    """
    symbol: str
    timeframe: str
    time_slot: str          # e.g. "09:30-09:35"
    slot_mean_volume: float
    slot_median_volume: float
    slot_std: float
    baseline_sessions_used: int
    baseline_computed_at: str   # ISO timestamp when this was computed


class RVOLResult(BaseModel):
    """Time-of-day normalized RVOL computation result.

    Compares current slot volume against historical same-slot baseline.
    Prevents apples-to-oranges comparison (opening vs. lunch volume).
    """
    current_volume: float
    slot_mean_volume: float
    slot_median_volume: float
    slot_std: float
    rvol_mean_ratio: float       # current_volume / slot_mean_volume
    rvol_median_ratio: float     # current_volume / slot_median_volume
    volume_percentile: float     # 0.0–100.0
    baseline_sessions_used: int
    time_slot: str
    normalized: bool             # True only if baseline was valid and used


# ---------------------------------------------------------------------------
# TradeabilityContext — Phase 8 inputs
# ---------------------------------------------------------------------------

class TradeabilityContext(BaseModel):
    """All deterministic evidence available when tradeability is evaluated.

    Constructed after trigger-bar close. Does NOT include options data.
    current_price is the observed underlying price at evaluation time —
    NOT a synthesised fill at trigger_price.
    """
    # The triggered setup being evaluated
    triggered_setup_id: str              # TriggeredSetupResult.playbook_evaluation_id
    playbook_id: str
    symbol: str
    timeframe: str
    direction: str                       # "BULLISH" | "BEARISH"
    trigger_price: float
    invalidation_price: float
    trigger_source_still_valid: bool = True

    # Current market snapshot
    current_price: float                 # observed underlying price — not a fill
    quote_age_seconds: float = 0.0

    # Bid/ask (optional — not always available for index instruments)
    bid: Optional[float] = None
    ask: Optional[float] = None

    # ATR
    atr: float

    # Volume
    current_volume: float = 0.0
    rvol_baseline: Optional[RVOLBaseline] = None

    # Delta / order flow
    delta_value: Optional[float] = None
    delta_provenance: DeltaProvenance = DeltaProvenance.UNAVAILABLE

    # Structural targets from Phase 6 (required for R:R)
    structural_target_candidates: List[float] = Field(default_factory=list)

    # Gap metadata from Phase 7 TriggerEvent
    gap_beyond_trigger: bool = False
    gap_distance_atr: float = 0.0

    # Setup age
    bars_since_trigger: int = 0
    seconds_since_trigger: float = 0.0

    # Timestamps
    triggered_at: str               # from TriggeredSetupResult.trigger_event_timestamp
    evaluation_timestamp: str       # when this tradeability check was performed

    # Publication state
    publication_state: PublicationState = PublicationState.VERIFIED


# ---------------------------------------------------------------------------
# TradeabilityResult — Phase 8 output
# ---------------------------------------------------------------------------

class TradeabilityResult(BaseModel):
    """Phase 8 Tradeability Assessment Result.

    Describes whether a TRIGGERED setup is currently tradeable.

    Invariants:
    - state is NEVER SignalState.EXECUTABLE
    - trade_state is ALWAYS "NONE - OPTIONS EXPRESSION NOT YET EVALUATED"
    - No option contract fields present
    - No portfolio/account risk fields present
    """
    tradeability_id: str
    triggered_setup_id: str
    playbook_id: str
    symbol: str
    timeframe: str
    direction: str

    state: TradeabilityState
    publication_state: PublicationState

    # Price references
    trigger_price: float
    observed_underlying_price: float     # current price at evaluation — not a fill
    invalidation_price: float
    target_candidates: List[float] = Field(default_factory=list)

    # Participation
    participation_score: float = 0.0             # 0–100
    participation_evidence_coverage: float = 0.0  # 0–1 (fraction of evidence available)

    # RVOL
    rvol_normalized: Optional[float] = None      # rvol_mean_ratio
    rvol_percentile: Optional[float] = None

    # Delta
    delta_score: float = 0.0            # 0–100, alignment × reliability
    delta_provenance: str = "UNAVAILABLE"
    delta_reliability: float = 0.0      # 0–1

    # Extension
    extension_atr: float = 0.0

    # Spread / liquidity
    spread_absolute: Optional[float] = None
    spread_pct: Optional[float] = None
    liquidity_status: str = "UNKNOWN"

    # Risk/Reward
    risk_reward_to_target1: Optional[float] = None
    risk_reward_to_best_structural_target: Optional[float] = None

    # Gap
    gap_beyond_trigger: bool = False
    gap_distance_atr: float = 0.0

    # Lifecycle
    bars_since_trigger: int = 0
    triggered_at: str = ""
    tradeability_evaluated_at: str = ""

    # Reason codes
    reason_codes: List[str] = Field(default_factory=list)

    # Full evidence ladder (for UI/debugging)
    evidence_ladder: Dict[str, Any] = Field(default_factory=dict)

    config_version: str = "research_v1"
    engine_version: str = "v8.0.0"

    # Phase invariant — must never be set by Phase 8
    trade_state: str = "NONE - OPTIONS EXPRESSION NOT YET EVALUATED"

    @model_validator(mode="after")
    def validate_phase8_invariants(self) -> "TradeabilityResult":
        if self.trade_state != "NONE - OPTIONS EXPRESSION NOT YET EVALUATED":
            raise ValueError(
                "Phase 8 Invariant Violation: trade_state must be "
                "'NONE - OPTIONS EXPRESSION NOT YET EVALUATED'. "
                "Options expression is Phase 9."
            )
        return self
