from qx.models.scan import RectangleMetrics, RuleResult, ScanCandidate
from qx.patterns.setup_intelligence import analyze_setup_intelligence


def test_candidate_quality_labels_are_score_based() -> None:
    candidate = ScanCandidate(
        symbol="TEST",
        status="reject",
        passed=False,
        score=0.82,
        setup_score=0.82,
        pattern_score=0.82,
        readiness_score=0.75,
        metrics=_metrics(),
        rules=[RuleResult(name="near_resistance", passed=False, value=0.5, threshold=0.85)],
    )

    assert candidate.quality_label == "Strong"
    assert candidate.display_status == "Strong Match"
    assert candidate.setup_status == "Near Breakout"
    assert candidate.failed_rule_names == ["near_resistance"]


def test_setup_intelligence_labels_strong_bullish_box_breakout() -> None:
    candidate = ScanCandidate(
        symbol="TEST",
        status="pass",
        passed=True,
        score=0.93,
        setup_score=0.93,
        pattern_score=0.90,
        readiness_score=0.95,
        metrics=_metrics(
            current_price=10.9,
            range_pct=0.06,
            position_in_range=0.90,
            resistance_distance_pct=0.005,
            avg_dollar_volume_20d=50_000_000,
            relative_volume_20d=1.35,
            target_1=12.2,
            risk_reward=1.5,
            ema20=10.4,
            box_status="Tight Box",
            trend_status="Aligned Uptrend",
            breakout_status="Ready",
            cahold_status="Confirmed",
            rs_status="Leading",
        ),
        rules=[RuleResult(name="near_resistance", passed=True, value=0.90, threshold=0.85)],
    )

    intelligence = analyze_setup_intelligence(candidate)

    assert intelligence.pattern_type == "BOX BO"
    assert intelligence.directional_bias == "Strong Bull"
    assert intelligence.breakout_quality_label == "Strong"
    assert intelligence.target_label == "Strong Target"
    assert intelligence.timing_read == "CAHOLD Ready"
    assert intelligence.trade_posture == "Review Now"


def test_setup_intelligence_marks_poor_structure_as_avoid() -> None:
    candidate = ScanCandidate(
        symbol="TEST",
        status="reject",
        passed=False,
        score=0.25,
        setup_score=0.25,
        pattern_score=0.20,
        readiness_score=0.10,
        metrics=_metrics(
            current_price=9.0,
            range_pct=0.18,
            position_in_range=-0.10,
            avg_dollar_volume_20d=5_000_000,
            relative_volume_20d=0.40,
            target_1=10.0,
            risk_reward=0.4,
            ema20=10.5,
            box_status="Poor Structure",
            trend_status="Weak",
            breakout_status="Below Support",
        ),
        rules=[RuleResult(name="tight_rectangle", passed=False, value=0.18, threshold=0.10)],
    )

    intelligence = analyze_setup_intelligence(candidate)

    assert intelligence.pattern_type == "RAW BD"
    assert intelligence.breakout_quality_label == "Weak"
    assert intelligence.timing_read == "Wait"
    assert intelligence.trade_posture == "Avoid"


def _metrics(**overrides: object) -> RectangleMetrics:
    values = {
        "support": 10,
        "resistance": 11,
        "current_price": 10.8,
        "range_pct": 0.10,
        "position_in_range": 0.80,
        "cross_up_count": 2,
        "cross_down_count": 2,
        "support_touches": 2,
        "resistance_touches": 2,
        "pivot_support_touches": 2,
        "pivot_resistance_touches": 2,
        "support_slope_pct": 0.01,
        "resistance_slope_pct": 0.01,
        "close_range_ratio": 0.7,
        "inside_close_pct": 0.9,
        "resistance_distance_pct": 0.02,
        "breakout_level": 11.11,
        "failure_level": 9.5,
        "stop_level": 9.8,
        "target_1": 11.8,
        "risk_reward": 1.1,
        "relative_volume_20d": 1.0,
        "avg_dollar_volume_20d": 25_000_000,
        "down_volume_ratio_10_to_20": 0.8,
        "volume_ratio_10_to_30": 0.9,
        "volume_ratio_30_to_50": 0.9,
        "atr_ratio_5_to_20": 0.7,
        "body_ratio_5": 0.5,
        "ema20": 10.2,
        "box_status": "Tight Box",
        "trend_status": "Aligned Uptrend",
        "breakout_status": "Ready",
    }
    values.update(overrides)
    return RectangleMetrics(
        **values,  # type: ignore[arg-type]
    )
