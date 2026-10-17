"""Phase 1: Rules Engine Configuration Loader & Validation."""

import json
from pathlib import Path
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class DirectionWeightsConfig(BaseModel):
    structure: float = 0.30
    vwap: float = 0.15
    ema: float = 0.10
    delta: float = 0.15
    sector_rs: float = 0.10
    market_alignment: float = 0.10
    higher_timeframe: float = 0.10


class DirectionLabelsConfig(BaseModel):
    bullish_min: float = 60.0
    lean_bullish_min: float = 20.0
    bearish_max: float = -60.0
    lean_bearish_max: float = -20.0


class EvidenceCoverageGatesConfig(BaseModel):
    partial: float = 0.60
    adequate: float = 0.75
    strong: float = 0.80
    complete: float = 0.85


class StructureScoresConfig(BaseModel):
    bullish_bos: float = 100.0
    bearish_bos: float = -100.0
    bullish_choch: float = 60.0
    bearish_choch: float = -60.0
    bullish_initial_break: float = 50.0
    bearish_initial_break: float = -50.0
    neutral: float = 0.0


class FreshnessConfig(BaseModel):
    stale_reliability_multiplier: float = 0.50
    structure_max_age_bars: Dict[str, int] = Field(default_factory=lambda: {"1m": 35, "5m": 25, "15m": 20})
    quote_max_age_seconds: float = 60.0


class DirectionEngineConfig(BaseModel):
    weights: DirectionWeightsConfig = Field(default_factory=DirectionWeightsConfig)
    structure_scores: StructureScoresConfig = Field(default_factory=StructureScoresConfig)
    freshness: FreshnessConfig = Field(default_factory=FreshnessConfig)
    delta_reliability: Dict[str, float] = Field(
        default_factory=lambda: {
            "ACTUAL_TRADE_AGGRESSOR": 1.00,
            "ESTIMATED_BID_ASK": 0.75,
            "BAR_DERIVED": 0.40,
            "UNAVAILABLE": 0.00,
        }
    )
    labels: DirectionLabelsConfig = Field(default_factory=DirectionLabelsConfig)
    evidence_coverage: EvidenceCoverageGatesConfig = Field(default_factory=EvidenceCoverageGatesConfig)
    sector_benchmarks: Dict[str, str] = Field(
        default_factory=lambda: {"NVDA": "XLK", "AAPL": "XLK", "MSFT": "XLK", "JPM": "XLF", "XOM": "XLE"}
    )
    timeframe_mapping: Dict[str, str] = Field(default_factory=lambda: {"1m": "5m", "5m": "15m"})


class VolatilityRegimeConfig(BaseModel):
    compressed_percentile_max: float = 30.0
    expanding_percentile_min: float = 70.0


class SessionRegimeConfig(BaseModel):
    opening_minutes: int = 30
    late_session_minutes: int = 60


class MarketRegimeConfig(BaseModel):
    volatility: VolatilityRegimeConfig = Field(default_factory=VolatilityRegimeConfig)
    session: SessionRegimeConfig = Field(default_factory=SessionRegimeConfig)


class PlaybookAConfig(BaseModel):
    version: str = "1.0"
    min_direction_score: float = 40.0
    direction_coverage_min: float = 0.75
    max_distance_to_zone_atr: float = 1.50
    allowed_regimes: List[str] = Field(default_factory=lambda: ["TREND_UP", "TREND_DOWN"])


class PlaybookBConfig(BaseModel):
    version: str = "1.0"
    max_approach_distance_atr: float = 1.50
    min_sweep_distance_atr: float = 0.10
    require_reclaim_setup: bool = True
    allowed_regimes: List[str] = Field(default_factory=lambda: ["RANGE", "TREND_UP", "TREND_DOWN"])


class PlaybookCConfig(BaseModel):
    version: str = "1.0"
    orb_minutes: int = 15
    direction_coverage_min: float = 0.75
    require_rth: bool = True
    max_extension_atr: float = 2.00
    allowed_regimes: List[str] = Field(default_factory=lambda: ["OPENING", "TREND_SESSION", "BALANCED", "LATE_SESSION"])


class OrderBlockValidationConfig(BaseModel):
    min_displacement_atr: float = 1.00
    min_body_multiplier: float = 1.50
    require_structural_consequence: bool = True
    zone_construction_mode: str = "BODY_TO_EXTREME"
    invalidation: Dict[str, Any] = Field(default_factory=lambda: {"mode": "CLOSE_BEYOND_DISTAL", "atr_buffer": 0.0})
    max_age_bars: Dict[str, int] = Field(default_factory=lambda: {"1m": 100, "5m": 50, "15m": 30})


class StructureConfig(BaseModel):
    break_confirmation: Dict[str, Any] = Field(default_factory=lambda: {"mode": "CLOSE", "min_buffer_atr": 0.0})
    protected_swing: Dict[str, Any] = Field(
        default_factory=lambda: {"max_leg_lookback_bars": {"1m": 35, "5m": 25, "15m": 20}}
    )


class TriggerConfirmationConfig(BaseModel):
    invalidation_precedence: str = "INVALIDATION_WINS"
    gap_handling: str = "OPEN_GAP_TRIGGERS"
    max_armed_bars: Dict[str, Any] = Field(
        default_factory=lambda: {
            "playbook_a_pullback": {"1m": 30, "5m": 12, "15m": 6},
            "playbook_b_liquidity_sweep": {"1m": 20, "5m": 8, "15m": 4},
            "playbook_c_orb_breakout": {"1m": 30, "5m": 12, "15m": 6},
        }
    )


class RVOLConfig(BaseModel):
    baseline_sessions: int = 20
    minimum_valid_sessions: int = 10
    slot_minutes: int = 5


class ParticipationWeightsConfig(BaseModel):
    rvol_mean_ratio: float = 0.40
    delta_alignment: float = 0.35
    volume_percentile: float = 0.25


class ParticipationConfig(BaseModel):
    weights: ParticipationWeightsConfig = Field(default_factory=ParticipationWeightsConfig)


class UnderlyingSpreadConfig(BaseModel):
    max_pct: float = 0.05


class DataFreshnessConfig(BaseModel):
    max_quote_age_seconds: float = 30.0
    max_rvol_age_seconds: float = 300.0
    max_delta_age_seconds: float = 30.0


class TargetSelectionPolicy(str, Enum):
    NEAREST_VALID_TARGET = "NEAREST_VALID_TARGET"
    BEST_VALID_TARGET = "BEST_VALID_TARGET"


class RiskRewardConfig(BaseModel):
    gate_target_policy: TargetSelectionPolicy = TargetSelectionPolicy.NEAREST_VALID_TARGET


class TradeabilityConfig(BaseModel):
    rvol: RVOLConfig = Field(default_factory=RVOLConfig)
    participation: ParticipationConfig = Field(default_factory=ParticipationConfig)
    risk_reward: RiskRewardConfig = Field(default_factory=RiskRewardConfig)
    max_extension_atr: Dict[str, float] = Field(
        default_factory=lambda: {
            "playbook_a_pullback": 1.0,
            "playbook_b_liquidity_sweep": 0.75,
            "playbook_c_orb_breakout": 1.5,
        }
    )
    min_risk_reward: Dict[str, float] = Field(
        default_factory=lambda: {
            "playbook_a_pullback": 1.5,
            "playbook_b_liquidity_sweep": 2.0,
            "playbook_c_orb_breakout": 1.5,
        }
    )
    max_tradeability_delay_bars: Dict[str, Any] = Field(
        default_factory=lambda: {
            "playbook_a_pullback": {"1m": 6, "5m": 3, "15m": 2},
            "playbook_b_liquidity_sweep": {"1m": 4, "5m": 2, "15m": 1},
            "playbook_c_orb_breakout": {"1m": 4, "5m": 2, "15m": 1},
        }
    )
    max_gap_distance_atr: Dict[str, float] = Field(
        default_factory=lambda: {
            "playbook_a_pullback": 2.0,
            "playbook_b_liquidity_sweep": 1.5,
            "playbook_c_orb_breakout": 2.0,
        }
    )
    underlying_spread: UnderlyingSpreadConfig = Field(default_factory=UnderlyingSpreadConfig)
    data_freshness: DataFreshnessConfig = Field(default_factory=DataFreshnessConfig)
    require_completed_bar_evidence: bool = True
    min_participation: Dict[str, float] = Field(
        default_factory=lambda: {
            "playbook_a_pullback": 25.0,
            "playbook_b_liquidity_sweep": 20.0,
            "playbook_c_orb_breakout": 35.0,
        }
    )
    min_participation_evidence_coverage: Dict[str, float] = Field(
        default_factory=lambda: {
            "playbook_a_pullback": 0.0,
            "playbook_b_liquidity_sweep": 0.0,
            "playbook_c_orb_breakout": 0.0,
        }
    )




# ─── Options Expression Configuration ─────────────────────────────────────────

class OptionsQuoteFreshnessConfig(BaseModel):
    max_age_seconds: float = 60.0

class OptionsLiquidityConfig(BaseModel):
    max_spread_pct: float = 0.15
    min_open_interest: int = 50
    min_volume: int = 10

class OptionsDteRange(BaseModel):
    min: int
    max: int

class OptionsDteConfig(BaseModel):
    playbook_windows: Dict[str, OptionsDteRange] = Field(
        default_factory=lambda: {
            "playbook_a_pullback": OptionsDteRange(min=7, max=45),
            "playbook_b_liquidity_sweep": OptionsDteRange(min=3, max=21),
            "playbook_c_orb_breakout": OptionsDteRange(min=0, max=5),
        }
    )

class OptionsVolatilityConfig(BaseModel):
    low_iv_rank_max: float = 35.0
    high_iv_rank_min: float = 60.0

class OptionsLongOptionConfig(BaseModel):
    delta_min: float = 0.40
    delta_max: float = 0.70

class OptionsDebitSpreadConfig(BaseModel):
    long_delta_min: float = 0.40
    long_delta_max: float = 0.70
    short_strike_target_policy: str = "STRUCTURAL_TARGET"

class OptionsCreditSpreadConfig(BaseModel):
    short_delta_min: float = 0.15
    short_delta_max: float = 0.35
    width: float = 5.0

class OptionsStrategyFitWeights(BaseModel):
    iv_fit: float = 0.20
    liquidity: float = 0.20
    structural_target_fit: float = 0.20
    dte_fit: float = 0.15
    greek_profile: float = 0.15
    event_risk: float = 0.10

class OptionsExpressionConfig(BaseModel):
    quote_freshness: OptionsQuoteFreshnessConfig = Field(default_factory=OptionsQuoteFreshnessConfig)
    liquidity: OptionsLiquidityConfig = Field(default_factory=OptionsLiquidityConfig)
    dte: OptionsDteConfig = Field(default_factory=OptionsDteConfig)
    volatility: OptionsVolatilityConfig = Field(default_factory=OptionsVolatilityConfig)
    long_option: OptionsLongOptionConfig = Field(default_factory=OptionsLongOptionConfig)
    debit_spread: OptionsDebitSpreadConfig = Field(default_factory=OptionsDebitSpreadConfig)
    credit_spread: OptionsCreditSpreadConfig = Field(default_factory=OptionsCreditSpreadConfig)
    strategy_fit_weights: OptionsStrategyFitWeights = Field(default_factory=OptionsStrategyFitWeights)
    iv_regime_bonus: float = 20.0
    structural_target_penalty: float = 20.0
    event_risk_penalty: float = 30.0
    event_risk_policy: str = "SCORE_PENALTY"



class PortfolioRiskPerTradeConfig(BaseModel):
    max_risk_pct_equity: float = 1.0

class PortfolioRiskDailyConfig(BaseModel):
    max_loss_pct_equity: float = 2.0
    max_loss_dollars: float = 2000.0

class PortfolioRiskBuyingPowerConfig(BaseModel):
    min_remaining_pct: float = 10.0

class PortfolioRiskConcentrationConfig(BaseModel):
    max_symbol_pct: float = 15.0
    max_sector_pct: float = 30.0

class PortfolioRiskGreeksConfig(BaseModel):
    max_abs_delta: Optional[float] = 2000.0
    max_abs_gamma: Optional[float] = 500.0
    max_abs_vega: Optional[float] = 1000.0
    max_negative_theta: Optional[float] = -500.0

class PortfolioRiskHedgePolicyConfig(BaseModel):
    allowance_enabled: bool = False

class PortfolioRiskCorrelationConfig(BaseModel):
    policy: Literal["FLAG_ONLY", "HARD_LIMIT"] = "FLAG_ONLY"
    max_group_exposure_pct: float = 30.0

class PortfolioRiskConfig(BaseModel):
    hedge_policy: PortfolioRiskHedgePolicyConfig = Field(default_factory=PortfolioRiskHedgePolicyConfig)
    hedge_allowance_enabled: bool = False  # Legacy for backwards compatibility
    per_trade: PortfolioRiskPerTradeConfig = Field(default_factory=PortfolioRiskPerTradeConfig)
    daily: PortfolioRiskDailyConfig = Field(default_factory=PortfolioRiskDailyConfig)
    buying_power: PortfolioRiskBuyingPowerConfig = Field(default_factory=PortfolioRiskBuyingPowerConfig)
    concentration: PortfolioRiskConcentrationConfig = Field(default_factory=PortfolioRiskConcentrationConfig)
    greek_limits: PortfolioRiskGreeksConfig = Field(default_factory=PortfolioRiskGreeksConfig)
    correlation: PortfolioRiskCorrelationConfig = Field(default_factory=PortfolioRiskCorrelationConfig)
    correlation_groups: Dict[str, List[str]] = Field(
        default_factory=lambda: {
            "semiconductor": ["NVDA", "AMD", "SMH", "SOXL"],
            "broad_index": ["SPY", "QQQ", "TQQQ", "SPX", "ES"]
        }
    )


class ShadowModeConfig(BaseModel):
    enabled: bool = True
    mode: Literal["EXPLICIT_SYMBOLS"] = "EXPLICIT_SYMBOLS"
    symbols: List[str] = Field(
        default_factory=lambda: [
            "SPY",
            "QQQ",
            "SPX",
            "NVDA",
            "AAPL",
            "MSFT",
            "TSLA",
            "AMD",
            "JPM",
            "XOM",
        ]
    )

    def includes(self, symbol: str) -> bool:
        return self.enabled and symbol.upper() in {item.upper() for item in self.symbols}

class MarketDriverThresholdsConfig(BaseModel):
    primary_activation_magnitude: float = 35.0
    secondary_activation_magnitude: float = 20.0
    weak_threshold: float = 35.0
    moderate_threshold: float = 55.0
    strong_threshold: float = 75.0
    hysteresis_delta: float = 10.0


class MarketDriverFreshnessConfig(BaseModel):
    quote_max_age_seconds: float = 30.0
    index_max_age_seconds: float = 60.0
    sector_max_age_seconds: float = 120.0
    delta_max_age_seconds: float = 60.0
    gamma_max_age_seconds: float = 900.0
    stale_reliability_multiplier: float = 0.50


class MarketDriverConfig(BaseModel):
    enabled: bool = True
    engine_version: str = "market_driver_v1.0.0"
    thresholds: MarketDriverThresholdsConfig = Field(default_factory=MarketDriverThresholdsConfig)
    freshness: MarketDriverFreshnessConfig = Field(default_factory=MarketDriverFreshnessConfig)
    min_coverage_sources: int = 3
    total_coverage_sources: int = 5
    max_secondary_drivers: int = 2
    max_confirming_evidence: int = 4
    max_conflicting_evidence: int = 4


class RulesEngineConfig(BaseModel):
    version: str = "research_v1"
    market_regime: MarketRegimeConfig = Field(default_factory=MarketRegimeConfig)
    direction_engine: DirectionEngineConfig = Field(default_factory=DirectionEngineConfig)
    playbooks: Dict[str, Any] = Field(default_factory=dict)
    order_block_validation: OrderBlockValidationConfig = Field(default_factory=OrderBlockValidationConfig)
    risk_limits: Dict[str, Any] = Field(default_factory=dict)
    structure: StructureConfig = Field(default_factory=StructureConfig)
    trigger_confirmation: TriggerConfirmationConfig = Field(default_factory=TriggerConfirmationConfig)
    tradeability: TradeabilityConfig = Field(default_factory=TradeabilityConfig)
    options_expression: OptionsExpressionConfig = Field(default_factory=OptionsExpressionConfig)
    portfolio_risk: PortfolioRiskConfig = Field(default_factory=PortfolioRiskConfig)
    shadow_mode: ShadowModeConfig = Field(default_factory=ShadowModeConfig)
    market_driver: MarketDriverConfig = Field(default_factory=MarketDriverConfig)


def load_rules_config(config_path: Path | None = None) -> RulesEngineConfig:
    """Load and parse versioned research configuration file."""
    if config_path is None:
        config_path = Path(__file__).parent / "rules_config_v1.json"

    if not config_path.exists():
        return RulesEngineConfig()


    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    mr_data = data.get("market_regime", {})
    vol_cfg = VolatilityRegimeConfig(**mr_data.get("volatility", {}))
    sess_cfg = SessionRegimeConfig(**mr_data.get("session", {}))
    market_regime_cfg = MarketRegimeConfig(volatility=vol_cfg, session=sess_cfg)

    de_data = data.get("direction_engine", {})
    dir_weights = DirectionWeightsConfig(**de_data.get("weights", {}))
    dir_struct_scores = StructureScoresConfig(**de_data.get("structure_scores", {}))
    dir_freshness = FreshnessConfig(**de_data.get("freshness", {}))
    dir_labels = DirectionLabelsConfig(**de_data.get("labels", {}))
    dir_cov = EvidenceCoverageGatesConfig(**de_data.get("evidence_coverage", {}))
    direction_engine_cfg = DirectionEngineConfig(
        weights=dir_weights,
        structure_scores=dir_struct_scores,
        freshness=dir_freshness,
        delta_reliability=de_data.get(
            "delta_reliability",
            {
                "ACTUAL_TRADE_AGGRESSOR": 1.00,
                "ESTIMATED_BID_ASK": 0.75,
                "BAR_DERIVED": 0.40,
                "UNAVAILABLE": 0.00,
            },
        ),
        labels=dir_labels,
        evidence_coverage=dir_cov,
        sector_benchmarks=de_data.get("sector_benchmarks", {"NVDA": "XLK", "AAPL": "XLK", "MSFT": "XLK", "JPM": "XLF", "XOM": "XLE"}),
        timeframe_mapping=de_data.get("timeframe_mapping", {"1m": "5m", "5m": "15m"}),
    )

    ob_val = OrderBlockValidationConfig(**data.get("order_block_validation", {}))
    struct_cfg = StructureConfig(**data.get("structure", {}))
    trig_cfg = TriggerConfirmationConfig(**data.get("trigger_confirmation", {}))

    # Phase 8: Tradeability config
    td_data = data.get("tradeability", {})
    td_rvol = RVOLConfig(**td_data.get("rvol", {}))
    td_part_data = td_data.get("participation", {})
    td_part_weights = ParticipationWeightsConfig(**td_part_data.get("weights", {}))
    td_participation = ParticipationConfig(weights=td_part_weights)
    td_spread = UnderlyingSpreadConfig(**td_data.get("underlying_spread", {}))
    td_freshness = DataFreshnessConfig(**td_data.get("data_freshness", {}))
    td_cfg = TradeabilityConfig(
        rvol=td_rvol,
        participation=td_participation,
        max_extension_atr=td_data.get("max_extension_atr", TradeabilityConfig().max_extension_atr),
        min_risk_reward=td_data.get("min_risk_reward", TradeabilityConfig().min_risk_reward),
        max_tradeability_delay_bars=td_data.get("max_tradeability_delay_bars", TradeabilityConfig().max_tradeability_delay_bars),
        max_gap_distance_atr=td_data.get("max_gap_distance_atr", TradeabilityConfig().max_gap_distance_atr),
        underlying_spread=td_spread,
        data_freshness=td_freshness,
        require_completed_bar_evidence=td_data.get("require_completed_bar_evidence", True),
        min_participation=td_data.get("min_participation", TradeabilityConfig().min_participation),
        min_participation_evidence_coverage=td_data.get("min_participation_evidence_coverage", TradeabilityConfig().min_participation_evidence_coverage),
    )


    # Phase 9: Options Expression config
    oe_data = data.get("options_expression", {})
    oe_fresh = OptionsQuoteFreshnessConfig(**oe_data.get("quote_freshness", {}))
    oe_liq = OptionsLiquidityConfig(**oe_data.get("liquidity", {}))
    
    dte_data = oe_data.get("dte", {})
    playbook_windows = {}
    playbook_windows_data = dte_data.get("playbook_windows", dte_data)
    if playbook_windows_data:
        for k, v in playbook_windows_data.items():
            playbook_windows[k] = OptionsDteRange(**v)
    oe_dte = OptionsDteConfig(playbook_windows=playbook_windows) if playbook_windows else OptionsDteConfig()
    
    oe_vol = OptionsVolatilityConfig(**oe_data.get("volatility", {}))
    oe_long = OptionsLongOptionConfig(**oe_data.get("long_option", {}))
    oe_debit = OptionsDebitSpreadConfig(**oe_data.get("debit_spread", {}))
    oe_credit = OptionsCreditSpreadConfig(**oe_data.get("credit_spread", {}))
    oe_weights = OptionsStrategyFitWeights(**oe_data.get("strategy_fit_weights", {}))
    
    oe_cfg = OptionsExpressionConfig(
        quote_freshness=oe_fresh,
        liquidity=oe_liq,
        dte=oe_dte,
        volatility=oe_vol,
        long_option=oe_long,
        debit_spread=oe_debit,
        credit_spread=oe_credit,
        strategy_fit_weights=oe_weights,
        iv_regime_bonus=oe_data.get("iv_regime_bonus", 20.0),
        structural_target_penalty=oe_data.get("structural_target_penalty", 20.0),
        event_risk_penalty=oe_data.get("event_risk_penalty", 30.0),
        event_risk_policy=oe_data.get("event_risk_policy", "SCORE_PENALTY"),
    )


    pr_data = data.get("portfolio_risk", {})
    
    hedge_policy_data = pr_data.get("hedge_policy", {})
    hedge_policy_cfg = PortfolioRiskHedgePolicyConfig(**hedge_policy_data)
    
    pr_cfg = PortfolioRiskConfig(
        hedge_policy=hedge_policy_cfg,
        per_trade=PortfolioRiskPerTradeConfig(**pr_data.get("per_trade", {})),
        daily=PortfolioRiskDailyConfig(**pr_data.get("daily", {})),
        buying_power=PortfolioRiskBuyingPowerConfig(**pr_data.get("buying_power", {})),
        concentration=PortfolioRiskConcentrationConfig(**pr_data.get("concentration", {})),
        greek_limits=PortfolioRiskGreeksConfig(**pr_data.get("greek_limits", {})),
        correlation=PortfolioRiskCorrelationConfig(**pr_data.get("correlation", {})),
        correlation_groups=pr_data.get("correlation_groups", PortfolioRiskConfig().correlation_groups),
        hedge_allowance_enabled=pr_data.get("hedge_allowance_enabled", hedge_policy_cfg.allowance_enabled)
    )
    shadow_cfg = ShadowModeConfig(**data.get("shadow_mode", {}))
    md_data = data.get("market_driver", {})
    md_thresholds = MarketDriverThresholdsConfig(**md_data.get("thresholds", {}))
    md_freshness = MarketDriverFreshnessConfig(**md_data.get("freshness", {}))
    md_cfg = MarketDriverConfig(
        enabled=md_data.get("enabled", True),
        engine_version=md_data.get("engine_version", "market_driver_v1.0.0"),
        thresholds=md_thresholds,
        freshness=md_freshness,
        min_coverage_sources=md_data.get("min_coverage_sources", 3),
        total_coverage_sources=md_data.get("total_coverage_sources", 5),
        max_secondary_drivers=md_data.get("max_secondary_drivers", 2),
        max_confirming_evidence=md_data.get("max_confirming_evidence", 4),
        max_conflicting_evidence=md_data.get("max_conflicting_evidence", 4),
    )
    return RulesEngineConfig(
        version=data.get("version", "research_v1"),
        market_regime=market_regime_cfg,
        direction_engine=direction_engine_cfg,
        playbooks=data.get("playbooks", {}),
        order_block_validation=ob_val,
        risk_limits=data.get("risk_limits", {}),
        structure=struct_cfg,
        trigger_confirmation=trig_cfg,
        tradeability=td_cfg,
        options_expression=oe_cfg,
        portfolio_risk=pr_cfg,
        shadow_mode=shadow_cfg,
        market_driver=md_cfg,
    )

