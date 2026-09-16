"""Phase 7: Entry Trigger & Confirmation Models.

Answers one question only:
DID THE PREVIOUSLY ARMED SETUP'S DEFINED TRIGGER ACTUALLY OCCUR?

State transition: ARMED -> TRIGGERED.
Prohibits EXECUTABLE state (tradeability is evaluated in Phase 8).
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

from qx.models.rules import PublicationState, RuleResult, SignalState


class TriggerRuleType(str, Enum):
    CLOSE_ABOVE_LEVEL = "CLOSE_ABOVE_LEVEL"
    CLOSE_BELOW_LEVEL = "CLOSE_BELOW_LEVEL"
    BODY_CLOSE_ABOVE_LEVEL = "BODY_CLOSE_ABOVE_LEVEL"
    BODY_CLOSE_BELOW_LEVEL = "BODY_CLOSE_BELOW_LEVEL"
    RECLAIM_ABOVE_LEVEL = "RECLAIM_ABOVE_LEVEL"
    RECLAIM_BELOW_LEVEL = "RECLAIM_BELOW_LEVEL"
    OPEN_GAP_ABOVE_LEVEL = "OPEN_GAP_ABOVE_LEVEL"
    OPEN_GAP_BELOW_LEVEL = "OPEN_GAP_BELOW_LEVEL"


class TriggerEvent(BaseModel):
    trigger_event_id: str
    playbook_id: str
    playbook_version: str = "1.0"
    symbol: str
    timeframe: str = "5m"
    direction: str = "NEUTRAL"
    trigger_source_type: str
    trigger_source_id: str
    trigger_price: float
    trigger_rule_type: TriggerRuleType
    event_timestamp: str
    knowledge_timestamp: str
    confirmed_at: str
    observed_price: float
    bar_open: float
    bar_high: float
    bar_low: float
    bar_close: float
    confirmation_method: str = "BAR_CLOSE_CONFIRMED"
    gap_beyond_trigger: bool = False
    gap_distance: float = 0.0
    gap_distance_atr: float = 0.0
    publication_state: PublicationState = PublicationState.VERIFIED
    source_playbook_evaluation_id: str
    rule_results: List[RuleResult] = Field(default_factory=list)
    config_version: str = "research_v1"
    engine_version: str = "v7.0.0"


class TriggeredSetupResult(BaseModel):
    playbook_evaluation_id: str
    playbook_id: str
    symbol: str
    timeframe: str = "5m"
    direction: str = "NEUTRAL"
    state: SignalState = SignalState.TRIGGERED
    trigger_event: Optional[TriggerEvent] = None
    armed_at: str
    trigger_level_known_at: str
    trigger_event_timestamp: str
    trigger_confirmed_at: str
    trigger_price: float
    invalidation_price: float
    publication_state: PublicationState = PublicationState.VERIFIED
    structure_valid: bool = True
    trigger_source_valid: bool = True
    evidence_ladder: Dict[str, Any] = Field(default_factory=dict)
    config_version: str = "research_v1"
    engine_version: str = "v7.0.0"
    trade_state: str = "NONE - TRADEABILITY NOT YET EVALUATED"

    @model_validator(mode="after")
    def validate_phase7_trigger_invariant(self):
        if self.state == SignalState.EXECUTABLE:
            raise ValueError(
                "Phase 7 Invariant Violation: 'EXECUTABLE' state is prohibited in Phase 7. "
                "Phase 7 only produces TRIGGERED."
            )
        if self.state == SignalState.TRIGGERED:
            if self.publication_state == PublicationState.BLOCKED:
                raise ValueError("Phase 7 Invariant Violation: BLOCKED publication state cannot trigger.")
            if self.trigger_event is None:
                raise ValueError("Phase 7 Invariant Violation: trigger_event is required when state is TRIGGERED.")
            if not self.armed_at:
                raise ValueError("Phase 7 Invariant Violation: armed_at timestamp is required.")
            if not self.trigger_level_known_at:
                raise ValueError("Phase 7 Invariant Violation: trigger_level_known_at timestamp is required.")
            if not self.trigger_event_timestamp:
                raise ValueError("Phase 7 Invariant Violation: trigger_event_timestamp is required.")
            if not self.trigger_confirmed_at:
                raise ValueError("Phase 7 Invariant Violation: trigger_confirmed_at is required.")
            if self.trigger_level_known_at > self.armed_at:
                raise ValueError("Phase 7.1 Temporal Causality Violation: trigger_level_known_at must be <= armed_at.")
            if self.armed_at >= self.trigger_event_timestamp:
                raise ValueError("Phase 7.1 Temporal Causality Violation: armed_at must be strictly < trigger_event_timestamp.")
            if self.trade_state != "NONE - TRADEABILITY NOT YET EVALUATED":
                raise ValueError(
                    "Phase 7 Invariant Violation: trade_state must be 'NONE - TRADEABILITY NOT YET EVALUATED'."
                )
        return self
