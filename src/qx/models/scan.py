from pydantic import BaseModel, Field


class RectangleScanParameters(BaseModel):
    lookback: int = Field(default=40, ge=20, le=120)
    use_prior_completed_box: bool = True
    min_range_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    max_range_pct: float = Field(default=0.10, gt=0.0, le=1.0)
    min_crossings_each_side: int = Field(default=2, ge=0)
    min_touches_each_side: int = Field(default=2, ge=0)
    touch_tolerance_pct: float = Field(default=0.08, ge=0.0, le=0.5)
    use_pivot_boundaries: bool = False
    require_pivot_touches: bool = False
    pivot_order: int = Field(default=2, ge=1, le=5)
    pivot_zone_tolerance_pct: float = Field(default=0.03, ge=0.0, le=0.20)
    require_flat_boundaries: bool = False
    max_boundary_slope_pct: float = Field(default=0.05, ge=0.0, le=1.0)
    min_close_range_ratio: float = Field(default=0.55, ge=0.0, le=1.0)
    min_bars_above_mid_pct: float = Field(default=0.55, ge=0.0, le=1.0)
    min_inside_close_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    breakout_buffer_pct: float = Field(default=0.01, ge=0.0, le=0.20)
    failure_atr_buffer_multiple: float = Field(default=0.5, ge=0.0, le=5.0)
    require_volume_staircase: bool = True
    vol_contraction_ratio: float = Field(default=0.95, gt=0.0, le=1.5)
    require_bullish_absorption: bool = True
    require_atr_compression: bool = True
    atr_compression_ratio: float = Field(default=0.75, gt=0.0, le=2.0)
    require_clean_recent_candles: bool = True
    min_body_ratio: float = Field(default=0.45, ge=0.0, le=1.0)
    require_prior_trend: bool = True
    require_base_above_50_sma: bool = True
    proximity_pct: float = Field(default=0.85, ge=0.0, le=1.5)
    max_resistance_distance_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    max_extension_pct: float = Field(default=1.02, ge=1.0, le=1.5)
    max_down_volume_expansion_ratio: float = Field(default=1.25, gt=0.0, le=10.0)
    min_price: float = Field(default=5.0, ge=0.0)
    min_avg_volume: int = Field(default=300_000, ge=0)


class RuleResult(BaseModel):
    name: str
    passed: bool
    value: float | int | str | bool
    threshold: float | int | str | bool
    details: str = ""


class RectangleMetrics(BaseModel):
    support: float
    resistance: float
    current_price: float = 0.0
    range_pct: float
    box_length: int = 0
    midpoint: float = 0.0
    position_in_range: float
    cross_up_count: int
    cross_down_count: int
    support_touches: int
    resistance_touches: int
    pivot_support_touches: int
    pivot_resistance_touches: int
    support_slope_pct: float
    resistance_slope_pct: float
    bars_above_mid_pct: float = 0.0
    close_range_ratio: float
    inside_close_pct: float
    resistance_distance_pct: float
    breakout_level: float
    failure_level: float
    stop_level: float = 0.0
    target_1: float = 0.0
    risk_reward: float = 0.0
    close_location: float = 0.0
    relative_volume_20d: float
    avg_volume_20d: float = 0.0
    avg_dollar_volume_20d: float = 0.0
    down_volume_ratio_10_to_20: float
    volume_ratio_10_to_30: float
    volume_ratio_30_to_50: float
    accumulation_ratio: float = 0.0
    cahold_count: int = 0
    absorption_score: float = 0.0
    atr_ratio_5_to_20: float
    body_ratio_5: float
    ema20: float = 0.0
    ema50: float = 0.0
    ema200: float = 0.0
    rsi14: float = 0.0
    adx14: float = 0.0
    box_quality_score: float = 0.0
    accumulation_score: float = 0.0
    breakout_score: float = 0.0
    box_status: str = "Unknown"
    volume_status: str = "Unknown"
    cahold_status: str = "Unknown"
    trend_status: str = "Unknown"
    ema_stack: str = "Unknown"
    rsi_status: str = "Unknown"
    adx_status: str = "Unknown"
    rs_status: str = "Not checked"
    breakout_status: str = "Unknown"
    retest_status: str = "Unknown"


class WeeklyContext(BaseModel):
    status: str
    score: float = Field(ge=0.0, le=1.0)
    close: float
    sma10: float
    sma30: float
    distance_to_10w_pct: float
    distance_to_30w_pct: float
    relative_volume_10w: float
    is_above_10w: bool
    is_above_30w: bool
    is_10w_above_30w: bool
    is_extended: bool


class ScanCandidate(BaseModel):
    symbol: str
    status: str
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    setup_score: float = Field(default=0.0, ge=0.0, le=1.0)
    pattern_score: float = Field(default=0.0, ge=0.0, le=1.0)
    readiness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    multi_timeframe_score: float = Field(default=0.0, ge=0.0, le=1.0)
    weekly_context: WeeklyContext | None = None
    metrics: RectangleMetrics
    rules: list[RuleResult]

    @property
    def quality_label(self) -> str:
        score = self.setup_score
        if score >= 0.90:
            return "Elite"
        if score >= 0.80:
            return "Strong"
        if score >= 0.70:
            return "Watch"
        if score >= 0.60:
            return "Developing"
        return "Weak"

    @property
    def display_status(self) -> str:
        return f"{self.quality_label} Match"

    @property
    def setup_status(self) -> str:
        if self.metrics.failure_level > 0 and self.metrics.position_in_range < 0:
            return "Invalidated"
        if self.metrics.breakout_level > 0 and self.metrics.position_in_range > 1.0:
            return "Breakout"
        if self.metrics.resistance_distance_pct <= 0.05 or self.metrics.position_in_range >= 0.85:
            return "Near Breakout"
        if self.metrics.position_in_range < 0:
            return "Below Support"
        return "Inside Base"

    @property
    def failed_rule_names(self) -> list[str]:
        return [rule.name for rule in self.rules if not rule.passed]


class ScanError(BaseModel):
    symbol: str
    message: str


class ScanRunResult(BaseModel):
    candidates: list[ScanCandidate]
    total_symbols: int
    passed_symbols: int
    failed_symbols: int = 0
    errors: list[ScanError] = Field(default_factory=list)
