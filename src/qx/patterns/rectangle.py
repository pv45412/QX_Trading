from dataclasses import dataclass

import numpy as np
import pandas as pd

from qx.models.scan import (
    RectangleMetrics,
    RectangleScanParameters,
    RuleResult,
    ScanCandidate,
)
from qx.patterns.weekly import analyze_weekly_context


@dataclass(frozen=True)
class _PivotBoundaries:
    support: float
    resistance: float
    support_touches: int
    resistance_touches: int


def analyze_rectangle(
    symbol: str,
    bars: pd.DataFrame,
    parameters: RectangleScanParameters | None = None,
) -> ScanCandidate:
    params = parameters or RectangleScanParameters()
    _validate_history(bars, params)

    box = _rectangle_window(bars, params)
    current = bars.iloc[-1]
    pivot_boundaries = _pivot_boundaries(box, params)

    raw_resistance = float(box["high"].max())
    raw_support = float(box["low"].min())
    if params.use_pivot_boundaries and pivot_boundaries is not None:
        support = pivot_boundaries.support
        resistance = pivot_boundaries.resistance
    else:
        support = raw_support
        resistance = raw_resistance
    rect_range = resistance - support
    valid_range = support > 0 and rect_range > 0
    midpoint = (resistance + support) / 2

    close = float(current["close"])
    range_pct = rect_range / support if valid_range else 0.0
    position = (close - support) / rect_range if valid_range else 0.0
    resistance_distance_pct = (resistance - close) / resistance if resistance > 0 else 0.0
    close_location = _close_location(current)
    close_range = float(box["close"].max() - box["close"].min())
    close_range_ratio = close_range / rect_range if valid_range else 0.0
    inside_close_pct = _inside_close_percentage(box, support, resistance) if valid_range else 0.0
    bars_above_mid_pct = float((box["close"] > midpoint).mean()) if valid_range and not box.empty else 0.0

    cross_up, cross_down = _count_midpoint_crosses(box["close"], midpoint)
    support_touches, resistance_touches = _count_boundary_touches(box, support, resistance, params)
    pivot_support_touches = pivot_boundaries.support_touches if pivot_boundaries else 0
    pivot_resistance_touches = pivot_boundaries.resistance_touches if pivot_boundaries else 0
    support_slope_pct, resistance_slope_pct = _boundary_slope_percentages(
        box,
        support,
        resistance,
        params,
    )
    vol10 = float(bars["volume"].tail(10).mean())
    vol30 = float(bars["volume"].tail(30).mean())
    vol50 = float(bars["volume"].tail(50).mean())
    avg_vol20 = float(bars["volume"].tail(20).mean())
    relative_volume_20d = float(current["volume"]) / avg_vol20 if avg_vol20 > 0 else 0.0
    recent_bars = bars.tail(10)
    up_vol = float(recent_bars.loc[recent_bars["close"] > recent_bars["open"], "volume"].sum())
    down_days = recent_bars.loc[recent_bars["close"] <= recent_bars["open"]]
    down_vol = float(down_days["volume"].sum())
    down_vol_avg = float(down_days["volume"].mean()) if not down_days.empty else 0.0
    down_volume_ratio_10_to_20 = down_vol_avg / avg_vol20 if avg_vol20 > 0 else 0.0
    accumulation_ratio = _accumulation_ratio(box)
    atr5, atr20 = _atr_values(bars)
    breakout_level = resistance * (1 + params.breakout_buffer_pct)
    failure_level = support - (atr20 * params.failure_atr_buffer_multiple)
    target_1 = resistance + rect_range if valid_range else 0.0
    stop_level = failure_level
    risk_reward = _risk_reward(close, stop_level, target_1)
    body_ratio = _body_ratio(bars.tail(5))
    sma50 = float(bars["close"].tail(50).mean())
    sma200 = float(bars["close"].tail(200).mean())
    ema20 = _last_ema(bars["close"], 20)
    ema50 = _last_ema(bars["close"], 50)
    ema200 = _last_ema(bars["close"], 200)
    rsi14 = _last_rsi(bars["close"], 14)
    adx14 = _last_adx(bars["high"], bars["low"], bars["close"], 14)
    cahold_count = _cahold_count(box, midpoint)

    rules = [
        RuleResult(
            name="valid_range",
            passed=valid_range,
            value=round(rect_range, 4),
            threshold="> 0",
            details="Support and resistance must define a usable box.",
        ),
        RuleResult(
            name="minimum_range_depth",
            passed=range_pct >= params.min_range_pct,
            value=round(range_pct, 4),
            threshold=params.min_range_pct,
            details="Avoids dead-flat shelves when a classic rectangle profile requires depth.",
        ),
        RuleResult(
            name="tight_rectangle",
            passed=range_pct <= params.max_range_pct,
            value=round(range_pct, 4),
            threshold=params.max_range_pct,
        ),
        RuleResult(
            name="support_touches",
            passed=support_touches >= params.min_touches_each_side,
            value=support_touches,
            threshold=params.min_touches_each_side,
        ),
        RuleResult(
            name="resistance_touches",
            passed=resistance_touches >= params.min_touches_each_side,
            value=resistance_touches,
            threshold=params.min_touches_each_side,
        ),
        RuleResult(
            name="pivot_support_touches",
            passed=not params.require_pivot_touches
            or pivot_support_touches >= params.min_touches_each_side,
            value=pivot_support_touches,
            threshold=_optional_threshold(params.require_pivot_touches, params.min_touches_each_side),
            details="Requires repeated local pivot lows near the same support zone.",
        ),
        RuleResult(
            name="pivot_resistance_touches",
            passed=not params.require_pivot_touches
            or pivot_resistance_touches >= params.min_touches_each_side,
            value=pivot_resistance_touches,
            threshold=_optional_threshold(params.require_pivot_touches, params.min_touches_each_side),
            details="Requires repeated local pivot highs near the same resistance zone.",
        ),
        RuleResult(
            name="flat_boundaries",
            passed=not params.require_flat_boundaries
            or (
                support_slope_pct <= params.max_boundary_slope_pct
                and resistance_slope_pct <= params.max_boundary_slope_pct
            ),
            value=f"{support_slope_pct:.4f}/{resistance_slope_pct:.4f}",
            threshold=_optional_threshold(
                params.require_flat_boundaries,
                params.max_boundary_slope_pct,
            ),
            details="Support and resistance touch zones should be mostly horizontal.",
        ),
        RuleResult(
            name="not_spike_defined",
            passed=close_range_ratio >= params.min_close_range_ratio,
            value=round(close_range_ratio, 4),
            threshold=params.min_close_range_ratio,
            details="Rejects boxes mostly defined by isolated wick spikes.",
        ),
        RuleResult(
            name="inside_close_containment",
            passed=inside_close_pct >= params.min_inside_close_pct,
            value=round(inside_close_pct, 4),
            threshold=params.min_inside_close_pct,
            details="Measures how many closes stayed inside the rectangle body.",
        ),
        RuleResult(
            name="midpoint_crosses_up",
            passed=cross_up >= params.min_crossings_each_side,
            value=cross_up,
            threshold=params.min_crossings_each_side,
        ),
        RuleResult(
            name="midpoint_crosses_down",
            passed=cross_down >= params.min_crossings_each_side,
            value=cross_down,
            threshold=params.min_crossings_each_side,
        ),
        RuleResult(
            name="midpoint_control",
            passed=bars_above_mid_pct >= params.min_bars_above_mid_pct,
            value=round(bars_above_mid_pct, 4),
            threshold=params.min_bars_above_mid_pct,
            details="Measures whether the box is living in the upper half instead of just crossing the midpoint.",
        ),
        RuleResult(
            name="volume_staircase",
            passed=not params.require_volume_staircase
            or (
                vol10 < vol30 * params.vol_contraction_ratio
                and vol30 < vol50 * params.vol_contraction_ratio
            ),
            value=f"{vol10:.0f}/{vol30:.0f}/{vol50:.0f}",
            threshold=_optional_threshold(
                params.require_volume_staircase,
                f"vol10 < vol30*{params.vol_contraction_ratio}, vol30 < vol50*{params.vol_contraction_ratio}",
            ),
        ),
        RuleResult(
            name="bullish_absorption",
            passed=not params.require_bullish_absorption or up_vol > down_vol,
            value=f"{up_vol:.0f}/{down_vol:.0f}",
            threshold=_optional_threshold(params.require_bullish_absorption, "up_vol > down_vol"),
        ),
        RuleResult(
            name="down_volume_not_expanding",
            passed=down_days.empty
            or down_vol_avg <= avg_vol20 * params.max_down_volume_expansion_ratio,
            value=round(down_volume_ratio_10_to_20, 4),
            threshold=params.max_down_volume_expansion_ratio,
            details="Rejects setups where recent down-day volume is expanding aggressively.",
        ),
        RuleResult(
            name="atr_compression",
            passed=not params.require_atr_compression
            or atr5 < atr20 * params.atr_compression_ratio,
            value=round(atr5 / atr20, 4) if atr20 > 0 else 0.0,
            threshold=_optional_threshold(params.require_atr_compression, params.atr_compression_ratio),
        ),
        RuleResult(
            name="clean_recent_candles",
            passed=not params.require_clean_recent_candles or body_ratio >= params.min_body_ratio,
            value=round(body_ratio, 4),
            threshold=_optional_threshold(params.require_clean_recent_candles, params.min_body_ratio),
        ),
        RuleResult(
            name="prior_trend",
            passed=not params.require_prior_trend or sma50 > sma200,
            value=round(sma50 / sma200, 4) if sma200 > 0 else 0.0,
            threshold=_optional_threshold(params.require_prior_trend, "sma50 > sma200"),
        ),
        RuleResult(
            name="price_above_50_200_sma",
            passed=close > sma50 and close > sma200,
            value=f"{close:.2f}/{sma50:.2f}/{sma200:.2f}",
            threshold="close > sma50 and close > sma200",
        ),
        RuleResult(
            name="base_above_50_sma",
            passed=not params.require_base_above_50_sma or support > sma50 * 0.97,
            value=round(support / sma50, 4) if sma50 > 0 else 0.0,
            threshold=_optional_threshold(
                params.require_base_above_50_sma,
                "support > sma50*0.97",
            ),
        ),
        RuleResult(
            name="near_resistance",
            passed=valid_range and _is_near_resistance(position, resistance_distance_pct, params),
            value=round(
                resistance_distance_pct if params.max_resistance_distance_pct > 0 else position,
                4,
            ),
            threshold=_near_resistance_threshold(params),
        ),
        RuleResult(
            name="not_extended",
            passed=close <= resistance * params.max_extension_pct,
            value=round(close / resistance, 4) if resistance > 0 else 0.0,
            threshold=params.max_extension_pct,
        ),
        RuleResult(
            name="not_failed_setup",
            passed=close >= failure_level,
            value=round(close / failure_level, 4) if failure_level > 0 else 0.0,
            threshold="close >= support - ATR buffer",
            details="Rejects setups that have failed below support plus the ATR buffer.",
        ),
        RuleResult(
            name="price_floor",
            passed=close >= params.min_price,
            value=round(close, 2),
            threshold=params.min_price,
        ),
        RuleResult(
            name="volume_floor",
            passed=avg_vol20 >= params.min_avg_volume,
            value=round(avg_vol20),
            threshold=params.min_avg_volume,
        ),
    ]

    passed_rules = sum(rule.passed for rule in rules)
    passed = passed_rules == len(rules)
    pattern_score = _weighted_score(
        rules,
        {
            "tight_rectangle": 3.0,
            "minimum_range_depth": 0.5,
            "support_touches": 1.5,
            "resistance_touches": 1.5,
            "pivot_support_touches": 1.0,
            "pivot_resistance_touches": 1.0,
            "flat_boundaries": 1.0,
            "not_spike_defined": 1.0,
            "inside_close_containment": 1.0,
            "midpoint_crosses_up": 1.0,
            "midpoint_crosses_down": 1.0,
            "midpoint_control": 1.5,
            "near_resistance": 2.5,
            "not_extended": 1.0,
            "not_failed_setup": 1.0,
        },
    )
    readiness_score = _weighted_score(
        rules,
        {
            "near_resistance": 3.0,
            "not_extended": 2.0,
            "not_failed_setup": 2.0,
            "volume_staircase": 1.5,
            "bullish_absorption": 1.0,
            "midpoint_control": 1.0,
            "down_volume_not_expanding": 1.0,
            "atr_compression": 1.5,
            "clean_recent_candles": 1.0,
            "price_above_50_200_sma": 1.0,
        },
    )
    setup_score = _apply_setup_caps(min(pattern_score, readiness_score), rules)
    weekly_context = analyze_weekly_context(bars)
    multi_timeframe_score = (setup_score * 0.70) + (weekly_context.score * 0.30)
    box_quality_score = _box_quality_score(rules)
    accumulation_score = _accumulation_score(
        accumulation_ratio=accumulation_ratio,
        bars_above_mid_pct=bars_above_mid_pct,
        cahold_count=cahold_count,
        rules=rules,
    )
    breakout_score = _breakout_score(
        position=position,
        resistance_distance_pct=resistance_distance_pct,
        close_location=close_location,
        rules=rules,
    )

    metrics = RectangleMetrics(
        support=support,
        resistance=resistance,
        current_price=close,
        range_pct=range_pct,
        box_length=len(box),
        midpoint=midpoint,
        position_in_range=position,
        cross_up_count=cross_up,
        cross_down_count=cross_down,
        support_touches=support_touches,
        resistance_touches=resistance_touches,
        pivot_support_touches=pivot_support_touches,
        pivot_resistance_touches=pivot_resistance_touches,
        support_slope_pct=support_slope_pct,
        resistance_slope_pct=resistance_slope_pct,
        bars_above_mid_pct=bars_above_mid_pct,
        close_range_ratio=close_range_ratio,
        inside_close_pct=inside_close_pct,
        resistance_distance_pct=resistance_distance_pct,
        breakout_level=breakout_level,
        failure_level=failure_level,
        stop_level=stop_level,
        target_1=target_1,
        risk_reward=risk_reward,
        close_location=close_location,
        relative_volume_20d=relative_volume_20d,
        avg_volume_20d=avg_vol20,
        avg_dollar_volume_20d=avg_vol20 * close,
        down_volume_ratio_10_to_20=down_volume_ratio_10_to_20,
        volume_ratio_10_to_30=vol10 / vol30 if vol30 > 0 else 0.0,
        volume_ratio_30_to_50=vol30 / vol50 if vol50 > 0 else 0.0,
        accumulation_ratio=accumulation_ratio,
        cahold_count=cahold_count,
        absorption_score=accumulation_score,
        atr_ratio_5_to_20=atr5 / atr20 if atr20 > 0 else 0.0,
        body_ratio_5=body_ratio,
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        rsi14=rsi14,
        adx14=adx14,
        box_quality_score=box_quality_score,
        accumulation_score=accumulation_score,
        breakout_score=breakout_score,
        box_status=_box_status(range_pct, support_touches, resistance_touches, bars_above_mid_pct, params),
        volume_status=_volume_status(accumulation_ratio, down_volume_ratio_10_to_20, relative_volume_20d),
        cahold_status=_cahold_status(cahold_count),
        trend_status=_trend_status(close, ema20, ema50, ema200),
        ema_stack=_ema_stack(close, ema20, ema50, ema200),
        rsi_status=_rsi_status(rsi14),
        adx_status=_adx_status(adx14),
        rs_status="Not checked",
        breakout_status=_breakout_status(position, resistance_distance_pct) if valid_range else "Invalid Range",
        retest_status=_retest_status(current, resistance, breakout_level),
    )

    return ScanCandidate(
        symbol=symbol.upper(),
        status="pass" if passed else "reject",
        passed=passed,
        score=passed_rules / len(rules),
        setup_score=setup_score,
        pattern_score=pattern_score,
        readiness_score=readiness_score,
        multi_timeframe_score=multi_timeframe_score,
        weekly_context=weekly_context,
        metrics=metrics,
        rules=rules,
    )


def _weighted_score(rules: list[RuleResult], weights: dict[str, float]) -> float:
    total_weight = sum(weights.values())
    if total_weight <= 0:
        return 0.0
    rule_map = {rule.name: rule.passed for rule in rules}
    passed_weight = sum(weight for name, weight in weights.items() if rule_map.get(name, False))
    return passed_weight / total_weight


def _box_quality_score(rules: list[RuleResult]) -> float:
    return _weighted_score(
        rules,
        {
            "tight_rectangle": 2.0,
            "minimum_range_depth": 1.0,
            "support_touches": 1.5,
            "resistance_touches": 1.5,
            "flat_boundaries": 1.0,
            "inside_close_containment": 1.0,
            "not_spike_defined": 1.0,
            "midpoint_control": 1.0,
        },
    )


def _accumulation_score(
    *,
    accumulation_ratio: float,
    bars_above_mid_pct: float,
    cahold_count: int,
    rules: list[RuleResult],
) -> float:
    ratio_score = max(0.0, min((accumulation_ratio - 0.85) / 0.65, 1.0))
    midpoint_score = max(0.0, min(bars_above_mid_pct / 0.65, 1.0))
    cahold_score = max(0.0, min(cahold_count / 3, 1.0))
    rule_map = {rule.name: rule.passed for rule in rules}
    contraction_score = 1.0 if rule_map.get("volume_staircase", False) else 0.0
    down_volume_score = 1.0 if rule_map.get("down_volume_not_expanding", False) else 0.0
    return (
        ratio_score * 0.30
        + midpoint_score * 0.25
        + cahold_score * 0.20
        + contraction_score * 0.15
        + down_volume_score * 0.10
    )


def _breakout_score(
    *,
    position: float,
    resistance_distance_pct: float,
    close_location: float,
    rules: list[RuleResult],
) -> float:
    position_score = max(0.0, min(position / 0.90, 1.0))
    distance_score = max(0.0, min((0.10 - resistance_distance_pct) / 0.10, 1.0))
    close_location_score = max(0.0, min(close_location / 0.70, 1.0))
    rule_map = {rule.name: rule.passed for rule in rules}
    clean_score = 1.0 if rule_map.get("not_extended", False) and rule_map.get("not_failed_setup", False) else 0.0
    return position_score * 0.35 + distance_score * 0.30 + close_location_score * 0.20 + clean_score * 0.15


def _apply_setup_caps(setup_score: float, rules: list[RuleResult]) -> float:
    rule_map = {rule.name: rule.passed for rule in rules}
    if not rule_map.get("valid_range", False):
        return 0.0
    if not rule_map.get("tight_rectangle", False):
        setup_score = min(setup_score, _wide_range_cap(rules))
    if not rule_map.get("minimum_range_depth", False):
        setup_score = min(setup_score, 0.69)
    if not rule_map.get("support_touches", False) or not rule_map.get("resistance_touches", False):
        setup_score = min(setup_score, 0.79)
    if not rule_map.get("pivot_support_touches", False) or not rule_map.get("pivot_resistance_touches", False):
        setup_score = min(setup_score, 0.79)
    if not rule_map.get("flat_boundaries", False):
        setup_score = min(setup_score, 0.69)
    if not rule_map.get("inside_close_containment", False):
        setup_score = min(setup_score, 0.69)
    if not rule_map.get("midpoint_crosses_up", False) or not rule_map.get("midpoint_crosses_down", False):
        setup_score = min(setup_score, 0.79)
    if not rule_map.get("midpoint_control", False):
        setup_score = min(setup_score, 0.84)
    if not rule_map.get("volume_staircase", False):
        setup_score = min(setup_score, 0.84)
    if not rule_map.get("down_volume_not_expanding", False):
        setup_score = min(setup_score, 0.69)
    if not rule_map.get("atr_compression", False):
        setup_score = min(setup_score, 0.84)
    if not rule_map.get("price_above_50_200_sma", False):
        setup_score = min(setup_score, 0.69)
    if not rule_map.get("near_resistance", False):
        setup_score = min(setup_score, 0.59)
    if not rule_map.get("not_extended", False):
        setup_score = min(setup_score, _extension_cap(rules))
    if not rule_map.get("not_failed_setup", False):
        setup_score = min(setup_score, 0.20)
    return setup_score


def _wide_range_cap(rules: list[RuleResult]) -> float:
    range_pct = _rule_float(rules, "tight_rectangle")
    threshold = _rule_threshold_float(rules, "tight_rectangle")
    if threshold <= 0:
        return 0.49

    severity = range_pct / threshold
    if severity >= 3.0:
        return 0.20
    if severity >= 2.0:
        return 0.30
    if severity >= 1.5:
        return 0.39
    return 0.49


def _extension_cap(rules: list[RuleResult]) -> float:
    position_vs_resistance = _rule_float(rules, "not_extended")
    if position_vs_resistance >= 1.05:
        return 0.25
    return 0.39


def _rule_float(rules: list[RuleResult], name: str) -> float:
    for rule in rules:
        if rule.name == name and isinstance(rule.value, int | float):
            return float(rule.value)
    return 0.0


def _is_near_resistance(
    position: float,
    resistance_distance_pct: float,
    params: RectangleScanParameters,
) -> bool:
    if position < 0:
        return False
    if params.max_resistance_distance_pct > 0:
        return resistance_distance_pct <= params.max_resistance_distance_pct
    return position >= params.proximity_pct


def _near_resistance_threshold(params: RectangleScanParameters) -> float:
    if params.max_resistance_distance_pct > 0:
        return params.max_resistance_distance_pct
    return params.proximity_pct


def _optional_threshold(required: bool, threshold: float | int | str) -> float | int | str:
    if required:
        return threshold
    return "disabled"


def _rule_threshold_float(rules: list[RuleResult], name: str) -> float:
    for rule in rules:
        if rule.name == name and isinstance(rule.threshold, int | float):
            return float(rule.threshold)
    return 0.0


def _validate_history(bars: pd.DataFrame, params: RectangleScanParameters) -> None:
    minimum_rows = minimum_required_bars(params)
    if len(bars) < minimum_rows:
        raise ValueError(f"Need at least {minimum_rows} daily bars, got {len(bars)}")
    required = ["open", "high", "low", "close", "volume"]
    if not set(required).issubset(bars.columns):
        raise ValueError("History requires open, high, low, close and volume columns")
    if not bars.index.is_unique or not bars.index.is_monotonic_increasing:
        raise ValueError("History must have unique, ascending bar indices")
    values = bars[required].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("History contains missing or non-finite OHLCV values")
    if (values[:, :4] <= 0).any() or (values[:, 4] < 0).any():
        raise ValueError("History requires positive prices and non-negative volume")


def minimum_required_bars(params: RectangleScanParameters) -> int:
    return max(200, 50, params.lookback + (1 if params.use_prior_completed_box else 0))


def _rectangle_window(bars: pd.DataFrame, params: RectangleScanParameters) -> pd.DataFrame:
    if params.use_prior_completed_box:
        return bars.iloc[-params.lookback - 1 : -1]
    return bars.iloc[-params.lookback :]


def _count_midpoint_crosses(closes: pd.Series, midpoint: float) -> tuple[int, int]:
    above = closes > midpoint
    cross_up = int((above & ~above.shift(1, fill_value=above.iloc[0])).sum())
    cross_down = int((~above & above.shift(1, fill_value=above.iloc[0])).sum())
    return cross_up, cross_down


def _accumulation_ratio(box: pd.DataFrame) -> float:
    if box.empty:
        return 0.0
    close_delta = box["close"].diff()
    up_volume = float(box.loc[close_delta > 0, "volume"].sum())
    down_volume = float(box.loc[close_delta < 0, "volume"].sum())
    if down_volume <= 0:
        return 2.0 if up_volume > 0 else 0.0
    return up_volume / down_volume


def _cahold_count(box: pd.DataFrame, midpoint: float) -> int:
    if len(box) < 20:
        return 0
    ema20 = box["close"].ewm(span=20, adjust=False).mean()
    avg_volume20 = box["volume"].rolling(20).mean()
    down_day = box["close"] < box["close"].shift(1)
    close_location = (box["close"] - box["low"]) / (box["high"] - box["low"]).replace(0, float("nan"))
    cahold = (
        down_day
        & (box["close"] > midpoint)
        & (box["close"] > ema20)
        & (box["volume"] <= avg_volume20)
        & (close_location >= 0.50)
    )
    return int(cahold.fillna(False).sum())


def _last_ema(series: pd.Series, span: int) -> float:
    if len(series) < span:
        return 0.0
    return float(series.astype(float).ewm(span=span, adjust=False).mean().iloc[-1])


def _last_rsi(close: pd.Series, length: int) -> float:
    if len(close) < length + 1:
        return 50.0
    delta = close.astype(float).diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / length, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / length, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    value = (100 - (100 / (1 + rs))).fillna(50).iloc[-1]
    return float(value)


def _last_adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> float:
    if len(close) < length + 2:
        return 0.0
    high_diff = high.astype(float).diff()
    low_diff = -low.astype(float).diff()
    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)
    true_range = pd.concat(
        [
            high.astype(float) - low.astype(float),
            (high.astype(float) - close.astype(float).shift(1)).abs(),
            (low.astype(float) - close.astype(float).shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    average_true_range = true_range.ewm(alpha=1 / length, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / length, adjust=False).mean() / average_true_range
    minus_di = 100 * minus_dm.ewm(alpha=1 / length, adjust=False).mean() / average_true_range
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
    return float(dx.ewm(alpha=1 / length, adjust=False).mean().fillna(0).iloc[-1])


def _close_location(row: pd.Series) -> float:
    high = float(row["high"])
    low = float(row["low"])
    if high <= low:
        return 0.0
    return (float(row["close"]) - low) / (high - low)


def _risk_reward(close: float, stop_level: float, target_1: float) -> float:
    risk = close - stop_level
    reward = target_1 - close
    if risk <= 0 or reward <= 0:
        return 0.0
    return reward / risk


def _box_status(
    range_pct: float,
    support_touches: int,
    resistance_touches: int,
    bars_above_mid_pct: float,
    params: RectangleScanParameters,
) -> str:
    if range_pct <= 0:
        return "Invalid"
    if range_pct <= params.max_range_pct and support_touches >= 2 and resistance_touches >= 2:
        return "Tight Box" if bars_above_mid_pct >= 0.55 else "Box Building"
    if range_pct <= 0.18 and support_touches >= 2 and resistance_touches >= 2:
        return "Wide Box"
    return "Poor Structure"


def _volume_status(accumulation_ratio: float, down_volume_ratio: float, relative_volume: float) -> str:
    if down_volume_ratio > 1.25:
        return "Distribution Risk"
    if accumulation_ratio >= 1.30:
        return "Accumulation"
    if accumulation_ratio >= 1.10:
        return "Constructive"
    if relative_volume < 0.80:
        return "Quiet"
    return "Neutral"


def _cahold_status(cahold_count: int) -> str:
    if cahold_count >= 3:
        return "Confirmed"
    if cahold_count >= 1:
        return "Present"
    return "Missing"


def _trend_status(close: float, ema20: float, ema50: float, ema200: float) -> str:
    if close > ema20 > ema50 > ema200:
        return "Aligned Uptrend"
    if close > ema50 > ema200:
        return "Constructive"
    if close < ema50:
        return "Weak"
    return "Mixed"


def _ema_stack(close: float, ema20: float, ema50: float, ema200: float) -> str:
    if not all([ema20, ema50, ema200]):
        return "Unavailable"
    if close > ema20 > ema50 > ema200:
        return "Price > 20 > 50 > 200"
    if close > ema50 > ema200:
        return "Price > 50 > 200"
    if close > ema200:
        return "Price > 200"
    return "Below 200"


def _rsi_status(rsi: float) -> str:
    if 50 <= rsi <= 70:
        return "Constructive"
    if rsi > 70:
        return "Extended"
    if 40 <= rsi < 50:
        return "Neutral"
    return "Weak"


def _adx_status(adx: float) -> str:
    if adx >= 25:
        return "Trend Strong"
    if adx >= 18:
        return "Trend Building"
    return "Low Trend"


def _breakout_status(position: float, resistance_distance_pct: float) -> str:
    if position < 0:
        return "Below Support"
    if position > 1.0:
        return "Breakout"
    if resistance_distance_pct <= 0.03 or position >= 0.90:
        return "Ready"
    if resistance_distance_pct <= 0.05 or position >= 0.85:
        return "Near Breakout"
    return "Inside Box"


def _retest_status(row: pd.Series, resistance: float, breakout_level: float) -> str:
    close = float(row["close"])
    low = float(row["low"])
    if resistance <= 0:
        return "Unknown"
    if close > breakout_level and low <= breakout_level:
        return "Breakout Retest"
    if close > resistance and low <= resistance:
        return "Box High Retest"
    if close > breakout_level:
        return "Extended Breakout"
    return "No Retest"


def _count_boundary_touches(
    box: pd.DataFrame,
    support: float,
    resistance: float,
    params: RectangleScanParameters,
) -> tuple[int, int]:
    tolerance = (resistance - support) * params.touch_tolerance_pct
    support_touches = int((box["low"] <= support + tolerance).sum())
    resistance_touches = int((box["high"] >= resistance - tolerance).sum())
    return support_touches, resistance_touches


def _inside_close_percentage(box: pd.DataFrame, support: float, resistance: float) -> float:
    if box.empty:
        return 0.0
    inside = (box["close"] >= support) & (box["close"] <= resistance)
    return float(inside.mean())


def _pivot_boundaries(box: pd.DataFrame, params: RectangleScanParameters) -> _PivotBoundaries | None:
    pivot_highs = _pivot_values(box["high"], params.pivot_order, is_high=True)
    pivot_lows = _pivot_values(box["low"], params.pivot_order, is_high=False)
    if not pivot_highs or not pivot_lows:
        return None

    resistance_anchor = max(pivot_highs)
    support_anchor = min(pivot_lows)
    resistance_cluster = [
        value
        for value in pivot_highs
        if resistance_anchor > 0
        and (resistance_anchor - value) / resistance_anchor <= params.pivot_zone_tolerance_pct
    ]
    support_cluster = [
        value
        for value in pivot_lows
        if support_anchor > 0 and (value - support_anchor) / support_anchor <= params.pivot_zone_tolerance_pct
    ]
    if not resistance_cluster or not support_cluster:
        return None

    return _PivotBoundaries(
        support=sum(support_cluster) / len(support_cluster),
        resistance=sum(resistance_cluster) / len(resistance_cluster),
        support_touches=len(support_cluster),
        resistance_touches=len(resistance_cluster),
    )


def _pivot_values(values: pd.Series, order: int, *, is_high: bool) -> list[float]:
    pivots: list[float] = []
    if len(values) < order * 2 + 1:
        return pivots

    for index in range(order, len(values) - order):
        current = float(values.iloc[index])
        left = values.iloc[index - order : index]
        right = values.iloc[index + 1 : index + order + 1]
        if is_high and current >= float(left.max()) and current >= float(right.max()):
            pivots.append(current)
        if not is_high and current <= float(left.min()) and current <= float(right.min()):
            pivots.append(current)
    return pivots


def _boundary_slope_percentages(
    box: pd.DataFrame,
    support: float,
    resistance: float,
    params: RectangleScanParameters,
) -> tuple[float, float]:
    tolerance = (resistance - support) * params.touch_tolerance_pct
    support_points = box.loc[box["low"] <= support + tolerance, "low"]
    resistance_points = box.loc[box["high"] >= resistance - tolerance, "high"]
    return _line_slope_pct(support_points), _line_slope_pct(resistance_points)


def _line_slope_pct(points: pd.Series) -> float:
    if len(points) < 2:
        return 0.0

    y_values = [float(value) for value in points.to_list()]
    x_values = list(range(len(y_values)))
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    denominator = sum((x_value - x_mean) ** 2 for x_value in x_values)
    if denominator <= 0 or y_mean <= 0:
        return 0.0

    slope = sum(
        (x_value - x_mean) * (y_value - y_mean)
        for x_value, y_value in zip(x_values, y_values, strict=True)
    ) / denominator
    projected_change = slope * (len(y_values) - 1)
    return abs(projected_change) / y_mean


def _atr_values(bars: pd.DataFrame) -> tuple[float, float]:
    high_low = bars["high"] - bars["low"]
    high_prev_close = (bars["high"] - bars["close"].shift(1)).abs()
    low_prev_close = (bars["low"] - bars["close"].shift(1)).abs()
    true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    return float(true_range.tail(5).mean()), float(true_range.tail(20).mean())


def _body_ratio(bars: pd.DataFrame) -> float:
    average_range = float((bars["high"] - bars["low"]).mean())
    if average_range <= 0:
        return 0.0
    average_body = float((bars["close"] - bars["open"]).abs().mean())
    return average_body / average_range
