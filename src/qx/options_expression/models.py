"""Phase 9 Options Expression Models."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class OptionsExpressionState(str, Enum):
    SUITABLE = "SUITABLE"
    NOT_SUITABLE = "NOT_SUITABLE"
    BLOCKED = "BLOCKED"


class StrategyType(str, Enum):
    LONG_CALL = "LONG_CALL"
    LONG_PUT = "LONG_PUT"
    CALL_DEBIT_SPREAD = "CALL_DEBIT_SPREAD"
    PUT_DEBIT_SPREAD = "PUT_DEBIT_SPREAD"
    BULL_PUT_SPREAD = "BULL_PUT_SPREAD"
    BEAR_CALL_SPREAD = "BEAR_CALL_SPREAD"


class OptionGreekProvenance(str, Enum):
    BROKER_PROVIDED = "BROKER_PROVIDED"
    MODEL_CALCULATED = "MODEL_CALCULATED"
    UNAVAILABLE = "UNAVAILABLE"


class OptionGreeks(BaseModel):
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    provenance: OptionGreekProvenance = OptionGreekProvenance.UNAVAILABLE
    # If MODEL_CALCULATED, specify these
    pricing_model: Optional[str] = None
    risk_free_rate: Optional[float] = None
    dividend_yield: Optional[float] = None
    volatility_input: Optional[float] = None
    calculation_timestamp: Optional[str] = None


class OptionContract(BaseModel):
    symbol: str
    underlying_symbol: str
    strike: float
    expiration: str  # YYYY-MM-DD
    dte: int
    is_call: bool
    bid: Optional[float] = None
    ask: Optional[float] = None
    mark: Optional[float] = None
    volume: int = 0
    open_interest: int = 0
    implied_volatility: Optional[float] = None
    greeks: OptionGreeks = Field(default_factory=OptionGreeks)
    quote_as_of: str
    quote_age_seconds: float = 0.0
    contract_multiplier: Optional[float] = None
    multiplier_provenance: str = "UNAVAILABLE"


class OptionsContext(BaseModel):
    """Deterministic options data provided for a specific underlying."""
    underlying_symbol: str
    underlying_price: float
    data_as_of: str
    
    # Expiration -> Strike -> "CALL" or "PUT" -> OptionContract
    chain: Dict[str, Dict[float, Dict[str, OptionContract]]] = Field(default_factory=dict)
    
    iv_raw: Optional[float] = None
    iv_rank: Optional[float] = None
    iv_percentile: Optional[float] = None
    iv_provenance: str = "UNAVAILABLE"
    iv_rank_provenance: str = "UNAVAILABLE"
    iv_percentile_provenance: str = "UNAVAILABLE"
    iv_data_as_of: Optional[str] = None
    
    # Known event dates (e.g. earnings, ex-div)
    events: List[Dict[str, Any]] = Field(default_factory=list)


class FillAssumptionType(str, Enum):
    NATURAL = "NATURAL"
    MIDPOINT_THEORETICAL = "MIDPOINT_THEORETICAL"
    CONSERVATIVE_ESTIMATE = "CONSERVATIVE_ESTIMATE"


class StrategyCandidate(BaseModel):
    candidate_id: str
    strategy_type: StrategyType
    direction: str
    expiration: str
    dte: int
    
    legs: List[OptionContract] = Field(default_factory=list)
    leg_quantities: List[int] = Field(default_factory=list) # e.g. [1, -1]
    
    net_debit: Optional[float] = None
    net_credit: Optional[float] = None
    max_loss: Optional[float] = None
    max_profit: Optional[float] = None
    breakeven_points: List[float] = Field(default_factory=list)
    
    combined_delta: Optional[float] = None
    combined_gamma: Optional[float] = None
    combined_theta: Optional[float] = None
    combined_vega: Optional[float] = None
    
    theta_per_day: Optional[float] = None
    theta_pct_of_debit: Optional[float] = None
    
    liquidity_status: str = "UNKNOWN"
    structural_target_fit: Optional[float] = None
    
    natural_price: Optional[float] = None
    midpoint_price: Optional[float] = None
    conservative_fill_estimate: Optional[float] = None
    fill_assumption: FillAssumptionType = FillAssumptionType.CONSERVATIVE_ESTIMATE
    
    strategy_fit_score: float = 0.0
    strategy_fit_components: Dict[str, float] = Field(default_factory=dict)
    
    structural_target_id: Optional[str] = None
    structural_target_price: Optional[float] = None
    short_strike: Optional[float] = None
    
    target_fit_distance: Optional[float] = None
    target_fit_score: Optional[float] = None

    event_risk_identified: bool = False
    events: List[Dict[str, Any]] = Field(default_factory=list)
    event_policy: str = "SCORE_PENALTY"
    event_penalty_applied: float = 0.0

    reason_codes: List[str] = Field(default_factory=list)
    evidence_ladder: Dict[str, Any] = Field(default_factory=dict)


class OptionsExpressionResult(BaseModel):
    expression_id: str
    tradeability_id: str
    playbook_id: str
    symbol: str
    direction: str
    
    state: OptionsExpressionState
    trade_state: str = "NONE - PORTFOLIO RISK NOT YET EVALUATED"
    
    underlying_price: float
    data_as_of: str
    evaluated_at: str
    publication_state: str
    
    iv: Optional[float] = None
    iv_rank: Optional[float] = None
    iv_percentile: Optional[float] = None
    volatility_regime: str = "UNKNOWN"
    
    event_risk: bool = False
    
    candidate_strategies: List[StrategyCandidate] = Field(default_factory=list)
    primary_candidate_id: Optional[str] = None
    
    structural_target_id: Optional[str] = None
    structural_target_price: Optional[float] = None
    short_strike: Optional[float] = None
    
    target_fit_distance: Optional[float] = None
    target_fit_score: Optional[float] = None

    event_risk_identified: bool = False
    events: List[Dict[str, Any]] = Field(default_factory=list)
    event_policy: str = "SCORE_PENALTY"
    event_penalty_applied: float = 0.0

    reason_codes: List[str] = Field(default_factory=list)
    evidence_ladder: Dict[str, Any] = Field(default_factory=dict)
    
    config_version: str
    engine_version: str

