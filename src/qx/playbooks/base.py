"""Phase 6: Common Playbook Evaluation Model & Base Evaluator.

Enforces strict Phase 6 lifecycle constraints:
Only NO_SETUP, WATCH, and ARMED are permitted states.
TRIGGERED and EXECUTABLE are strictly prohibited in Phase 6.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

from qx.models.rules import MarketRegimeModel, PublicationState, RuleResult, SignalState
from qx.playbooks.context import QXEvaluationContext


class PlaybookEvaluation(BaseModel):
    playbook_id: str
    playbook_version: str = "1.0"
    symbol: str
    timeframe: str = "5m"
    direction: str = "NEUTRAL"  # "BULLISH", "BEARISH", "NEUTRAL"
    state: SignalState = SignalState.NO_SETUP  # NO_SETUP, WATCH, ARMED
    setup_detected: bool = False
    reason_code: str = "NO_STRUCTURAL_CONTEXT"
    setup_quality_components: Dict[str, float] = Field(default_factory=dict)
    trigger_definition: str = ""
    trigger_price: Optional[float] = None
    trigger_source_type: str = ""
    trigger_source_id: str = ""
    trigger_knowledge_timestamp: str = ""
    invalidation_price: Optional[float] = None
    invalidation_source_type: str = ""
    invalidation_source_id: str = ""
    invalidation_knowledge_timestamp: str = ""
    structural_target_candidates: List[float] = Field(default_factory=list)
    publication_state: PublicationState = PublicationState.VERIFIED
    direction_score: float = 0.0
    direction_evidence_coverage: float = 1.0
    market_regime: MarketRegimeModel
    source_structure_event_ids: List[str] = Field(default_factory=list)
    source_order_block_ids: List[str] = Field(default_factory=list)
    source_pivot_ids: List[str] = Field(default_factory=list)
    rule_results: List[RuleResult] = Field(default_factory=list)
    event_timestamp: str = ""
    knowledge_timestamp: str = ""
    config_version: str = "research_v1"
    engine_version: str = "v6.1.0"
    trade_state: str = "NONE - PLAYBOOK NOT EVALUATED FOR TRADE EXECUTION IN PHASE 6"

    @model_validator(mode="after")
    def validate_phase6_lifecycle_invariant(self):
        disallowed_states = {SignalState.TRIGGERED, SignalState.EXECUTABLE}
        if self.state in disallowed_states:
            raise ValueError(
                f"Phase 6 Invariant Violation: Playbook state '{self.state.value}' is prohibited in Phase 6. "
                "Only NO_SETUP, WATCH, and ARMED states are permitted."
            )
        if self.state == SignalState.ARMED:
            if not self.setup_detected:
                raise ValueError("ARMED invariant violation: setup_detected must be True")
            if not self.trigger_definition:
                raise ValueError("ARMED invariant violation: trigger_definition is required")
            if self.trigger_price is None:
                raise ValueError("ARMED invariant violation: trigger_price is required for price-based triggers")
            if self.invalidation_price is None:
                raise ValueError("ARMED invariant violation: invalidation_price is required")
            if not self.trigger_source_type:
                raise ValueError("ARMED invariant violation: trigger_source_type is required")
            if not self.invalidation_source_type:
                raise ValueError("ARMED invariant violation: invalidation_source_type is required")
            if self.reason_code != "SETUP_FORMED_WAITING_FOR_TRIGGER":
                raise ValueError("ARMED invariant violation: reason_code must be 'SETUP_FORMED_WAITING_FOR_TRIGGER'")
            if not self.invalidation_knowledge_timestamp:
                raise ValueError("ARMED invariant violation: invalidation_knowledge_timestamp is required")
        return self


class BasePlaybookEvaluator(ABC):
    """Abstract Base Class for QX Playbook Evaluators."""

    playbook_id: str
    playbook_version: str = "1.0"

    @abstractmethod
    def evaluate(self, ctx: QXEvaluationContext) -> PlaybookEvaluation:
        """Evaluates setup eligibility and returns a PlaybookEvaluation model."""
        pass
