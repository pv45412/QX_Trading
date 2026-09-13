from dataclasses import dataclass

from qx.models.scan import ScanCandidate


@dataclass(frozen=True)
class SetupIntelligence:
    pattern_type: str
    directional_bias: str
    bias_ready_pct: float
    target_upside_pct: float
    target_label: str
    breakout_quality_pct: float
    breakout_quality_label: str
    timing_read: str
    trade_posture: str


def analyze_setup_intelligence(candidate: ScanCandidate) -> SetupIntelligence:
    """Translate raw rectangle metrics into watchlist-style decision labels.

    This is a presentation/ranking layer. It intentionally does not change the
    rectangle pass/fail rules.
    """
    bull_pct = _bull_ready_pct(candidate)
    bear_pct = _bear_ready_pct(candidate)
    bias = _directional_bias(bull_pct, bear_pct)
    quality_pct = _breakout_quality_pct(candidate)
    target_pct = _target_upside_pct(candidate)
    return SetupIntelligence(
        pattern_type=_pattern_type(candidate),
        directional_bias=bias,
        bias_ready_pct=max(bull_pct, bear_pct),
        target_upside_pct=target_pct,
        target_label=_target_label(target_pct),
        breakout_quality_pct=quality_pct,
        breakout_quality_label=_quality_label(quality_pct),
        timing_read=_timing_read(candidate),
        trade_posture=_trade_posture(candidate, bias, quality_pct),
    )


def _pattern_type(candidate: ScanCandidate) -> str:
    metrics = candidate.metrics
    if metrics.box_status in {"Tight Box", "Box Building", "Wide Box"}:
        if metrics.breakout_status in {"Breakout", "Ready", "Near Breakout"}:
            return "BOX BO"
        if metrics.position_in_range < 0:
            return "BOX BD"
        return "BOX"
    if metrics.breakout_status == "Breakout":
        return "RAW BO"
    if metrics.position_in_range < 0:
        return "RAW BD"
    return "NONE"


def _bull_ready_pct(candidate: ScanCandidate) -> float:
    metrics = candidate.metrics
    checks = [
        metrics.avg_dollar_volume_20d >= 20_000_000,
        metrics.range_pct <= 0.08 and metrics.range_pct > 0,
        metrics.trend_status in {"Aligned Uptrend", "Constructive"},
        metrics.relative_volume_20d >= 0.80,
        metrics.relative_volume_20d >= 1.20 or metrics.resistance_distance_pct <= 0.0075,
        metrics.atr_ratio_5_to_20 <= 1.0 if metrics.atr_ratio_5_to_20 > 0 else False,
        metrics.position_in_range >= 0.70,
        metrics.support_touches >= 2 and metrics.resistance_touches >= 2,
        metrics.breakout_status in {"Breakout", "Ready", "Near Breakout"},
        metrics.current_price > metrics.ema20 if metrics.ema20 > 0 else False,
    ]
    return _pct(checks)


def _bear_ready_pct(candidate: ScanCandidate) -> float:
    metrics = candidate.metrics
    checks = [
        metrics.avg_dollar_volume_20d >= 20_000_000,
        metrics.range_pct <= 0.08 and metrics.range_pct > 0,
        metrics.trend_status == "Weak",
        metrics.relative_volume_20d >= 0.80,
        metrics.relative_volume_20d >= 1.20 or metrics.position_in_range <= 0.30,
        metrics.atr_ratio_5_to_20 <= 1.0 if metrics.atr_ratio_5_to_20 > 0 else False,
        metrics.position_in_range <= 0.30,
        metrics.support_touches >= 2 and metrics.resistance_touches >= 2,
        metrics.position_in_range < 0 or metrics.breakout_status == "Below Support",
        metrics.current_price < metrics.ema20 if metrics.ema20 > 0 else False,
    ]
    return _pct(checks)


def _breakout_quality_pct(candidate: ScanCandidate) -> float:
    metrics = candidate.metrics
    checks = [
        metrics.range_pct <= 0.07 and metrics.range_pct > 0,
        metrics.avg_dollar_volume_20d >= 20_000_000,
        metrics.rs_status not in {"Weak", "Lagging"},
        metrics.trend_status in {"Aligned Uptrend", "Constructive"},
        metrics.position_in_range >= 0.70,
        -0.002 <= metrics.resistance_distance_pct <= 0.02,
        metrics.relative_volume_20d >= 0.80,
        metrics.atr_ratio_5_to_20 <= 1.0 if metrics.atr_ratio_5_to_20 > 0 else False,
    ]
    return _pct(checks)


def _directional_bias(bull_pct: float, bear_pct: float) -> str:
    if bull_pct >= 0.80 and bull_pct > bear_pct:
        return "Strong Bull"
    if bear_pct >= 0.80 and bear_pct > bull_pct:
        return "Strong Bear"
    if bull_pct >= 0.60 and bull_pct > bear_pct:
        return "Watch Bull"
    if bear_pct >= 0.60 and bear_pct > bull_pct:
        return "Watch Bear"
    return "No Edge"


def _target_upside_pct(candidate: ScanCandidate) -> float:
    close = candidate.metrics.current_price
    target = candidate.metrics.target_1
    if close <= 0 or target <= close:
        return 0.0
    return (target - close) / close


def _target_label(target_pct: float) -> str:
    if target_pct >= 0.10:
        return "Strong Target"
    if target_pct >= 0.05:
        return "Decent Target"
    return "Low Target"


def _quality_label(quality_pct: float) -> str:
    if quality_pct >= 0.875:
        return "Strong"
    if quality_pct >= 0.625:
        return "Watch"
    return "Weak"


def _timing_read(candidate: ScanCandidate) -> str:
    metrics = candidate.metrics
    if metrics.breakout_status == "Breakout":
        if metrics.retest_status in {"Breakout Retest", "Box High Retest"}:
            return "BO Retest"
        return "Fresh BO"
    if metrics.cahold_status in {"Confirmed", "Present"} and metrics.breakout_status in {
        "Ready",
        "Near Breakout",
    }:
        return "CAHOLD Ready"
    if metrics.breakout_status in {"Ready", "Near Breakout"}:
        return "Near Trigger"
    if metrics.cahold_status in {"Confirmed", "Present"}:
        return "Pullback Hold"
    return "Wait"


def _trade_posture(candidate: ScanCandidate, bias: str, quality_pct: float) -> str:
    if candidate.setup_status == "Invalidated" or candidate.metrics.box_status == "Poor Structure":
        return "Avoid"
    if bias == "Strong Bull" and quality_pct >= 0.875 and candidate.metrics.risk_reward >= 1.0:
        return "Review Now"
    if bias in {"Strong Bull", "Watch Bull"} and candidate.metrics.breakout_status in {
        "Ready",
        "Near Breakout",
        "Breakout",
    }:
        return "Watch Trigger"
    if bias in {"Strong Bear", "Watch Bear"}:
        return "Bearish Watch"
    return "Monitor"


def _pct(checks: list[bool]) -> float:
    if not checks:
        return 0.0
    return sum(1 for check in checks if check) / len(checks)
