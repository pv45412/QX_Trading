"""Phase 6: Shared Evaluation Context for Playbooks.

Prevents redundant recomputation of SMC structure, Order Blocks, Direction Engine,
and Market Regime by providing a unified evaluation context for all playbooks.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from qx.config.rules_config import RulesEngineConfig, load_rules_config
from qx.direction.direction_engine import DirectionEngineResult
from qx.models.rules import MarketRegimeModel, PublicationState


class QXEvaluationContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    symbol: str
    timeframe: str = "5m"
    bars: List[Dict[str, Any]] = Field(default_factory=list)
    latest_bar: Dict[str, Any] = Field(default_factory=dict)
    market_regime: MarketRegimeModel
    direction: DirectionEngineResult
    structure_result: Optional[Any] = None
    order_blocks: List[Any] = Field(default_factory=list)
    fvgs: List[Dict[str, Any]] = Field(default_factory=list)
    session_levels: Dict[str, Any] = Field(default_factory=dict)  # PDH, PDL, SWING_HIGH, SWING_LOW, EQH, EQL, etc.
    vwap: Optional[float] = None
    atr: Optional[float] = 1.0
    publication_state: PublicationState = PublicationState.VERIFIED
    event_timestamp: str = ""
    knowledge_timestamp: str = ""
    rules_config: Optional[RulesEngineConfig] = None
