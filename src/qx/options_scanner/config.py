"""Versioned runtime configuration for QX Options Scanner V1.

Single source of truth for all thresholds, spread limits, weights, EWMA parameters,
DTE ranges, and risk limits. No magic numbers in code.
"""

from typing import Dict, List, Literal
from pydantic import BaseModel, Field


class LiquidityConfig(BaseModel):
    max_option_spread_pct: float = Field(default=0.08, description="Max option bid-ask spread relative to mid price (8%)")
    min_open_interest: int = Field(default=100, description="Minimum open interest required per contract")
    min_volume: int = Field(default=10, description="Minimum daily volume per contract")


class BlackoutConfig(BaseModel):
    normal_mode_earnings_days: int = Field(default=5, description="Days before/after earnings to trigger EARNINGS_BLACKOUT in Normal Mode")
    fomc_cpi_event_hours: int = Field(default=48, description="Hours before FOMC/CPI events to trigger EVENT_BLACKOUT")


class EWMAParameters(BaseModel):
    span: int = Field(default=20, description="EWMA span for forward realized volatility proxy")
    decay_lambda: float = Field(default=0.94, description="Lambda decay factor")
    annualization_factor: float = Field(default=252.0**0.5, description="Trading days annualization multiplier")


class DirectionWeights(BaseModel):
    market_structure_bos_choch: float = Field(default=0.25)
    vwap_alignment: float = Field(default=0.15)
    ema_slope_alignment: float = Field(default=0.15)
    rvol: float = Field(default=0.15)
    cumulative_delta: float = Field(default=0.15)
    fvg_quality: float = Field(default=0.10)
    relative_strength: float = Field(default=0.05)


class VolatilityWeights(BaseModel):
    iv_rank_percentile: float = Field(default=0.25)
    iv_vs_forecast_rv: float = Field(default=0.35)
    skew_25d: float = Field(default=0.15)
    term_structure: float = Field(default=0.15)
    expected_move_fit: float = Field(default=0.10)


class OverallWeights(BaseModel):
    market_regime_alignment: float = Field(default=0.15)
    direction_quality: float = Field(default=0.55)
    strategy_vol_fit: float = Field(default=0.30)


class GradeThresholds(BaseModel):
    a_plus: float = Field(default=90.0)
    a: float = Field(default=80.0)
    b: float = Field(default=70.0)


class RiskSizingTiers(BaseModel):
    a_plus_max_risk_pct: float = Field(default=0.0100, description="1.00% equity risk for A+")
    a_plus_min_risk_pct: float = Field(default=0.0075, description="0.75% equity risk for A+")
    a_max_risk_pct: float = Field(default=0.0075, description="0.75% equity risk for A")
    a_min_risk_pct: float = Field(default=0.0050, description="0.50% equity risk for A")
    b_max_risk_pct: float = Field(default=0.0050, description="0.50% equity risk for B")
    b_min_risk_pct: float = Field(default=0.0025, description="0.25% equity risk for B")


class DTERanges(BaseModel):
    intraday: tuple[int, int] = (1, 7)
    swing: tuple[int, int] = (14, 45)
    premium: tuple[int, int] = (21, 60)
    wheel: tuple[int, int] = (30, 45)
    leaps: tuple[int, int] = (180, 730)


class TargetDeltas(BaseModel):
    debit_long_delta: float = Field(default=0.60, description="Long leg delta for debit spread (0.55-0.65)")
    debit_short_delta: float = Field(default=0.30, description="Short leg delta for debit spread (0.25-0.35)")
    credit_short_delta: float = Field(default=0.25, description="Short leg delta for credit spread/wheel (0.25-0.30)")
    leap_long_delta: float = Field(default=0.80, description="LEAP long leg delta (0.75-0.85)")
    pmcc_short_delta: float = Field(default=0.25, description="PMCC short leg delta (0.25-0.30)")
    long_single_delta: float = Field(default=0.60, description="Single option long delta (0.55-0.70)")


class ScannerConfig(BaseModel):
    config_version: str = Field(default="1.0.0")
    mode: Literal["normal", "event"] = Field(default="normal")
    max_data_age_seconds: int = Field(default=900, description="15 minutes data freshness veto limit")
    liquidity: LiquidityConfig = Field(default_factory=LiquidityConfig)
    blackouts: BlackoutConfig = Field(default_factory=BlackoutConfig)
    ewma: EWMAParameters = Field(default_factory=EWMAParameters)
    direction_weights: DirectionWeights = Field(default_factory=DirectionWeights)
    volatility_weights: VolatilityWeights = Field(default_factory=VolatilityWeights)
    overall_weights: OverallWeights = Field(default_factory=OverallWeights)
    grades: GradeThresholds = Field(default_factory=GradeThresholds)
    risk: RiskSizingTiers = Field(default_factory=RiskSizingTiers)
    dte_ranges: DTERanges = Field(default_factory=DTERanges)
    deltas: TargetDeltas = Field(default_factory=TargetDeltas)


def get_scanner_config() -> ScannerConfig:
    return ScannerConfig()
