import pandas as pd

from qx.data.metadata import SymbolMetadata, SymbolMetadataStore
from qx.models.scan import ScanCandidate
from qx.patterns.ranking import composite_rank_score
from qx.patterns.setup_intelligence import analyze_setup_intelligence


def candidate_metadata(
    candidates: list[ScanCandidate],
    *,
    metadata_store: SymbolMetadataStore | None = None,
    max_metadata_enrichment: int = 100,
) -> dict[str, SymbolMetadata]:
    """Resolve display metadata for scanner candidates without changing scanner rules."""
    metadata_store = metadata_store or SymbolMetadataStore()
    symbols = [candidate.symbol for candidate in candidates]
    metadata_store.enrich_yfinance(symbols, max_symbols=max_metadata_enrichment)
    return {symbol: metadata_store.get(symbol) for symbol in symbols}


def candidate_table(
    candidates: list[ScanCandidate],
    *,
    metadata_by_symbol: dict[str, SymbolMetadata] | None = None,
) -> pd.DataFrame:
    rows = []
    for candidate in candidates:
        intelligence = analyze_setup_intelligence(candidate)
        rows.append(
            {
                "ticker": candidate.symbol,
                "symbol": candidate.symbol,
                "sector": _candidate_sector(candidate, metadata_by_symbol),
                "industry": _candidate_industry(candidate, metadata_by_symbol),
                "pattern_type": intelligence.pattern_type,
                "directional_bias": intelligence.directional_bias,
                "bias_ready_pct": round(intelligence.bias_ready_pct, 3),
                "target_upside_pct": round(intelligence.target_upside_pct, 4),
                "target_label": intelligence.target_label,
                "breakout_quality_pct": round(intelligence.breakout_quality_pct, 3),
                "breakout_quality_label": intelligence.breakout_quality_label,
                "timing_read": intelligence.timing_read,
                "trade_posture": intelligence.trade_posture,
                "price": round(candidate.metrics.current_price, 2),
                "market_cap": 0.0,
                "avg_dollar_volume": round(candidate.metrics.avg_dollar_volume_20d, 0),
                "quality": candidate.quality_label,
                "setup_status": candidate.setup_status,
                "box_status": candidate.metrics.box_status,
                "box_length": candidate.metrics.box_length,
                "box_height_pct": round(candidate.metrics.range_pct, 4),
                "box_high": round(candidate.metrics.resistance, 2),
                "box_low": round(candidate.metrics.support, 2),
                "box_mid": round(candidate.metrics.midpoint, 2),
                "upper_touches": candidate.metrics.resistance_touches,
                "lower_touches": candidate.metrics.support_touches,
                "bars_above_mid_pct": round(candidate.metrics.bars_above_mid_pct, 4),
                "vol_status": candidate.metrics.volume_status,
                "accum_ratio": round(candidate.metrics.accumulation_ratio, 3),
                "rvol": round(candidate.metrics.relative_volume_20d, 3),
                "cahold_status": candidate.metrics.cahold_status,
                "cahold_count": candidate.metrics.cahold_count,
                "absorption_score": round(candidate.metrics.absorption_score, 3),
                "trend_status": candidate.metrics.trend_status,
                "ema_stack": candidate.metrics.ema_stack,
                "rsi_status": candidate.metrics.rsi_status,
                "adx_status": candidate.metrics.adx_status,
                "rs_status": candidate.metrics.rs_status,
                "breakout_status": candidate.metrics.breakout_status,
                "close_location": round(candidate.metrics.close_location, 4),
                "retest_status": candidate.metrics.retest_status,
                "box_quality_score": round(candidate.metrics.box_quality_score, 3),
                "accum_score": round(candidate.metrics.accumulation_score, 3),
                "breakout_score": round(candidate.metrics.breakout_score, 3),
                "qx_rect_score": round(composite_rank_score(candidate), 3),
                "qx_action": rectangle_action(candidate),
                "stop_level": round(candidate.metrics.stop_level, 2),
                "target_1": round(candidate.metrics.target_1, 2),
                "risk_reward": round(candidate.metrics.risk_reward, 2),
                "rank_score": round(composite_rank_score(candidate), 3),
                "setup_score": round(candidate.setup_score, 3),
                "pattern_score": round(candidate.pattern_score, 3),
                "readiness_score": round(candidate.readiness_score, 3),
                "mtf_score": round(candidate.multi_timeframe_score, 3),
                "weekly_status": (
                    candidate.weekly_context.status if candidate.weekly_context else "Unknown"
                ),
                "weekly_extension": (
                    candidate.weekly_context.is_extended if candidate.weekly_context else False
                ),
                "rule_score": round(candidate.score, 3),
                "support": round(candidate.metrics.support, 2),
                "resistance": round(candidate.metrics.resistance, 2),
                "range_pct": round(candidate.metrics.range_pct, 4),
                "position": round(candidate.metrics.position_in_range, 4),
                "resistance_distance_pct": round(candidate.metrics.resistance_distance_pct, 4),
                "support_touches": candidate.metrics.support_touches,
                "resistance_touches": candidate.metrics.resistance_touches,
                "pivot_support_touches": candidate.metrics.pivot_support_touches,
                "pivot_resistance_touches": candidate.metrics.pivot_resistance_touches,
                "support_slope_pct": round(candidate.metrics.support_slope_pct, 4),
                "resistance_slope_pct": round(candidate.metrics.resistance_slope_pct, 4),
                "close_range_ratio": round(candidate.metrics.close_range_ratio, 4),
                "inside_close_pct": round(candidate.metrics.inside_close_pct, 4),
                "breakout_level": round(candidate.metrics.breakout_level, 2),
                "failure_level": round(candidate.metrics.failure_level, 2),
                "relative_volume_20d": round(candidate.metrics.relative_volume_20d, 3),
                "down_volume_ratio_10_to_20": round(candidate.metrics.down_volume_ratio_10_to_20, 3),
                "missing": ", ".join(candidate.failed_rule_names[:3]),
            }
        )
    frame = pd.DataFrame(rows)
    return cast_existing_columns(
        frame,
        {
            "ticker": "string",
            "symbol": "string",
            "sector": "string",
            "industry": "string",
            "pattern_type": "string",
            "directional_bias": "string",
            "bias_ready_pct": "float64",
            "target_upside_pct": "float64",
            "target_label": "string",
            "breakout_quality_pct": "float64",
            "breakout_quality_label": "string",
            "timing_read": "string",
            "trade_posture": "string",
            "price": "float64",
            "market_cap": "float64",
            "avg_dollar_volume": "float64",
            "quality": "string",
            "setup_status": "string",
            "box_status": "string",
            "box_length": "int64",
            "box_height_pct": "float64",
            "box_high": "float64",
            "box_low": "float64",
            "box_mid": "float64",
            "upper_touches": "int64",
            "lower_touches": "int64",
            "bars_above_mid_pct": "float64",
            "vol_status": "string",
            "accum_ratio": "float64",
            "rvol": "float64",
            "cahold_status": "string",
            "cahold_count": "int64",
            "absorption_score": "float64",
            "trend_status": "string",
            "ema_stack": "string",
            "rsi_status": "string",
            "adx_status": "string",
            "rs_status": "string",
            "breakout_status": "string",
            "close_location": "float64",
            "retest_status": "string",
            "box_quality_score": "float64",
            "accum_score": "float64",
            "breakout_score": "float64",
            "qx_rect_score": "float64",
            "qx_action": "string",
            "stop_level": "float64",
            "target_1": "float64",
            "risk_reward": "float64",
            "rank_score": "float64",
            "setup_score": "float64",
            "pattern_score": "float64",
            "readiness_score": "float64",
            "mtf_score": "float64",
            "weekly_status": "string",
            "weekly_extension": "bool",
            "rule_score": "float64",
            "support": "float64",
            "resistance": "float64",
            "range_pct": "float64",
            "position": "float64",
            "resistance_distance_pct": "float64",
            "support_touches": "int64",
            "resistance_touches": "int64",
            "pivot_support_touches": "int64",
            "pivot_resistance_touches": "int64",
            "support_slope_pct": "float64",
            "resistance_slope_pct": "float64",
            "close_range_ratio": "float64",
            "inside_close_pct": "float64",
            "breakout_level": "float64",
            "failure_level": "float64",
            "relative_volume_20d": "float64",
            "down_volume_ratio_10_to_20": "float64",
            "missing": "string",
        },
    )


def _candidate_sector(
    candidate: ScanCandidate,
    metadata_by_symbol: dict[str, SymbolMetadata] | None,
) -> str:
    if metadata_by_symbol is None:
        return "Unknown"
    return metadata_by_symbol.get(candidate.symbol, SymbolMetadata(symbol=candidate.symbol)).sector


def _candidate_industry(
    candidate: ScanCandidate,
    metadata_by_symbol: dict[str, SymbolMetadata] | None,
) -> str:
    if metadata_by_symbol is None:
        return "Unknown"
    return metadata_by_symbol.get(candidate.symbol, SymbolMetadata(symbol=candidate.symbol)).industry


def rectangle_dashboard_columns() -> list[str]:
    return [
        "ticker",
        "sector",
        "industry",
        "price",
        "market_cap",
        "avg_dollar_volume",
        "pattern_type",
        "directional_bias",
        "bias_ready_pct",
        "breakout_quality_label",
        "breakout_quality_pct",
        "target_label",
        "target_upside_pct",
        "timing_read",
        "trade_posture",
        "box_status",
        "box_length",
        "box_height_pct",
        "box_high",
        "box_low",
        "box_mid",
        "upper_touches",
        "lower_touches",
        "bars_above_mid_pct",
        "vol_status",
        "accum_ratio",
        "rvol",
        "cahold_status",
        "cahold_count",
        "absorption_score",
        "trend_status",
        "ema_stack",
        "rsi_status",
        "adx_status",
        "rs_status",
        "breakout_status",
        "breakout_level",
        "close_location",
        "retest_status",
        "box_quality_score",
        "accum_score",
        "breakout_score",
        "qx_rect_score",
        "qx_action",
        "stop_level",
        "target_1",
        "risk_reward",
        "missing",
    ]


def rectangle_detail_columns() -> list[str]:
    return [
        "ticker",
        "market_cap",
        "avg_dollar_volume",
        "box_high",
        "box_low",
        "box_mid",
        "cahold_status",
        "cahold_count",
        "absorption_score",
        "rsi_status",
        "adx_status",
        "rs_status",
        "breakout_level",
        "retest_status",
        "box_quality_score",
        "accum_score",
        "breakout_score",
        "stop_level",
        "target_1",
        "missing",
    ]


def rectangle_action(candidate: ScanCandidate) -> str:
    metrics = candidate.metrics
    if candidate.setup_status == "Invalidated" or metrics.box_status == "Poor Structure":
        return "Reject"
    if metrics.breakout_status == "Breakout":
        return "Breakout"
    if metrics.retest_status in {"Breakout Retest", "Box High Retest"}:
        return "Retest"
    if (
        candidate.setup_score >= 0.85
        and metrics.accumulation_score >= 0.65
        and metrics.breakout_score >= 0.75
    ):
        return "A+ Ready"
    if metrics.breakout_status in {"Ready", "Near Breakout"} and candidate.setup_score >= 0.70:
        return "Ready"
    if metrics.box_status in {"Tight Box", "Box Building"} and candidate.setup_score >= 0.55:
        return "Watch"
    return "Early Base"


def rules_table(candidate: ScanCandidate) -> pd.DataFrame:
    frame = pd.DataFrame([rule.model_dump() for rule in candidate.rules])
    return cast_existing_columns(
        frame,
        {
            "name": "string",
            "passed": "bool",
            "value": "string",
            "threshold": "string",
            "details": "string",
        },
    )


def cast_existing_columns(frame: pd.DataFrame, dtype_map: dict[str, str]) -> pd.DataFrame:
    existing_map = {column: dtype for column, dtype in dtype_map.items() if column in frame.columns}
    return frame.astype(existing_map)
