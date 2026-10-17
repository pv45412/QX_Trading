from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from qx.config.rules_config import RulesEngineConfig
from qx.direction.direction_engine import DirectionEngineResult
from qx.market_driver.models import MarketDriverResult
from qx.models.rules import PublicationState
from qx.options_expression.models import OptionsContext, OptionsExpressionResult
from qx.playbooks.base import PlaybookEvaluation
from qx.portfolio.models import AccountRiskContext, PortfolioRiskResult
from qx.regime.market_regime import MarketRegimeModel
from qx.structure.smc_suite import SMCAnalysisResult
from qx.tradeability.models import TradeabilityResult
from qx.triggers.models import TriggeredSetupResult


PIPELINE_VERSION = "core_v1"
SKIPPED = "SKIPPED"


class LifecycleState(str, Enum):
    BLOCKED = "BLOCKED"
    NO_SETUP = "NO_SETUP"
    WATCH = "WATCH"
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    NOT_TRADEABLE = "NOT_TRADEABLE"
    EXPIRED = "EXPIRED"
    TRADEABLE = "TRADEABLE"
    OPTIONS_NOT_SUITABLE = "OPTIONS_NOT_SUITABLE"
    OPTIONS_SUITABLE = "OPTIONS_SUITABLE"
    PORTFOLIO_VETOED = "PORTFOLIO_VETOED"
    PORTFOLIO_APPROVED = "PORTFOLIO_APPROVED"


class UnderlyingQuoteSnapshot(BaseModel):
    symbol: str
    last_price: float
    bid: float
    ask: float
    volume: int
    timestamp: datetime


class ExternalIOMetric(BaseModel):
    operation: str
    source: str
    elapsed_ms: float = Field(ge=0.0)
    calls: int = Field(default=1, ge=0)
    cache_hits: int = Field(default=0, ge=0)
    cache_misses: int = Field(default=0, ge=0)
    status: str = "OK"


class DataDependencyStatus(BaseModel):
    name: str
    available: bool = False
    source: str = "UNAVAILABLE"
    data_as_of: Optional[datetime] = None
    freshness: str = "UNAVAILABLE"
    publication_state: str = "BLOCKED"
    sync_status: str = "UNAVAILABLE"
    reason_code: Optional[str] = None
    cache_status: str = "MISS"
    snapshot_id: Optional[int] = None
    quality_status: Optional[str] = None
    quality_reason_codes: List[str] = Field(default_factory=list)
    requested_timeframe: Optional[str] = None
    observed_timeframe: Optional[str] = None
    bar_count: Optional[int] = None
    usable_bar_count: Optional[int] = None
    incomplete_candle_count: Optional[int] = None
    retrieved_at: Optional[datetime] = None
    content_sha256: Optional[str] = None


class QXEvaluationContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    symbol: str
    timeframe: str = "5m"
    evaluation_timestamp: datetime
    request_started_at: Optional[datetime] = None
    bars: Any = None
    armed_playbook: Optional[PlaybookEvaluation] = None
    quote: Optional[UnderlyingQuoteSnapshot] = None
    option_chain: Optional[OptionsContext] = None
    account_snapshot: Optional[AccountRiskContext] = None
    session_open_str: str = "09:30:00"
    session_close_str: str = "16:00:00"
    publication_state: PublicationState = PublicationState.RESEARCH_ONLY

    gex_data: Optional[Dict[str, float]] = None
    gamma_value: float = 0.0
    gamma_provenance: str = "UNAVAILABLE"

    delta_value: float = 0.0
    delta_provenance: str = "UNAVAILABLE"
    delta_age_seconds: int = 9999

    vwap: float = 0.0
    vwap_slope: float = 0.0
    vwap_age_seconds: int = 9999

    fast_ema: float = 0.0
    medium_ema: float = 0.0
    slow_ema: float = 0.0
    fast_slope: float = 0.0
    medium_slope: float = 0.0
    slow_slope: float = 0.0
    ema_age_seconds: int = 9999

    relative_strength_score: float = 0.0
    sector_rs_age_seconds: int = 9999
    market_alignment_score: float = 0.0
    market_alignment_age_seconds: int = 9999
    is_index_future: bool = False

    htf_structure_state: str = "UNKNOWN"
    htf_age_bars: int = 9999
    horizon: Optional[str] = None
    htf_timeframe: Optional[str] = None
    htf_bars: Any = None
    htf_structure: Optional[SMCAnalysisResult] = None
    macro_timeframe: Optional[str] = None
    macro_bars: Any = None
    delta_reliability_map: Dict[str, float] = Field(default_factory=dict)

    atr: float = 0.0
    structural_target_candidates: List[float] = Field(default_factory=list)
    external_io_ms: Optional[float] = None
    cache_hits: Optional[int] = None
    cache_misses: Optional[int] = None
    data_dependencies: Dict[str, DataDependencyStatus] = Field(default_factory=dict)
    io_metrics: List[ExternalIOMetric] = Field(default_factory=list)
    previous_market_driver: Optional[MarketDriverResult] = None

    config_version: str = "research_v1"
    config: Optional[RulesEngineConfig] = None


StageLatency = Union[float, int, Literal["SKIPPED"]]


class QXEvaluationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    symbol: str
    timeframe: str
    evaluation_timestamp: datetime
    request_started_at: Optional[datetime] = None
    publication_state: PublicationState = PublicationState.RESEARCH_ONLY
    horizon: Optional[str] = None
    htf_timeframe: Optional[str] = None
    htf_structure: Optional[SMCAnalysisResult] = None
    macro_timeframe: Optional[str] = None

    structure: Optional[SMCAnalysisResult] = None
    market_regime: Optional[MarketRegimeModel] = None
    direction: Optional[DirectionEngineResult] = None
    playbooks: Optional[List[PlaybookEvaluation]] = None
    primary_playbook_candidate: Optional[PlaybookEvaluation] = None
    trigger: Optional[TriggeredSetupResult] = None
    tradeability: Optional[TradeabilityResult] = None
    options_expression: Optional[OptionsExpressionResult] = None
    portfolio_risk: Optional[PortfolioRiskResult] = None
    market_driver: Optional[MarketDriverResult] = None

    current_lifecycle_state: LifecycleState
    evidence_summary: List[str] = Field(default_factory=list)
    reason_codes: List[str] = Field(default_factory=list)

    config_version: str
    pipeline_version: str = PIPELINE_VERSION
    engine_versions: Dict[str, str] = Field(default_factory=dict)
    stage_latencies: Dict[str, StageLatency] = Field(default_factory=dict)
    data_dependencies: Dict[str, DataDependencyStatus] = Field(default_factory=dict)
    io_metrics: List[ExternalIOMetric] = Field(default_factory=list)
    evaluated_bar_window_sha256: Optional[str] = None

    @property
    def evaluated_at(self) -> datetime:
        return self.evaluation_timestamp

    @property
    def latency_ms(self) -> Dict[str, StageLatency]:
        return self.stage_latencies
