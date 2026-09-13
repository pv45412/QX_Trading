import json
import math
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


COLUMN_LABELS = {
    "accum_ratio": "Accum Ratio",
    "accum_score": "Accum",
    "adx_status": "ADX",
    "above_sma50_pct": "Above 50SMA",
    "above_sma200_pct": "Above 200SMA",
    "aggression_score": "Aggression",
    "ask": "Ask",
    "avg_dollar_volume": "Avg Dollar Vol",
    "avg_volume_20d": "Avg Vol 20D",
    "avg_rank": "Avg Rank",
    "avg_rank_score": "Avg Rank",
    "avg_setup_score": "Avg Setup",
    "breakout_level": "Breakout Level",
    "breakout_quality_label": "BO Grade",
    "breakout_quality_pct": "BO Quality",
    "breakout_setup_score": "Breakout Setup",
    "breakout_score": "Breakout Score",
    "breakout_status": "Breakout Status",
    "bid": "Bid",
    "breadth_score": "Breadth",
    "breadth_source": "Breadth Source",
    "breadth_status": "Breadth Status",
    "bars_above_mid_pct": "Above Mid",
    "box_height_pct": "Box Height",
    "box_high": "Box High",
    "box_length": "Box Length",
    "box_low": "Box Low",
    "box_mid": "Box Mid",
    "box_quality_score": "Box Quality",
    "box_status": "Box Status",
    "cahold_count": "CAHOLD Count",
    "cahold_status": "CAHOLD",
    "close_location": "Close Location",
    "close_location_20d": "20D Location",
    "confirmation_status": "Confirmation",
    "confirmed_heavyweights": "Confirmed",
    "constituents_checked": "Checked",
    "created_at": "Created",
    "current_rank": "Current Rank",
    "current_score": "Current Score",
    "current_status": "Current Status",
    "distance_from_sma20": "From 20SMA",
    "distance_from_sma50": "From 50SMA",
    "distance_to_prior_high": "To Prior High",
    "distance_to_prior_low": "From Prior Low",
    "distance_to_resistance": "To Resistance",
    "distance_to_trigger": "To Trigger",
    "distance_to_trigger_pct": "To Trigger",
    "directional_bias": "Bias",
    "directional_read": "Flow Read",
    "down_volume_ratio_10_to_20": "Down Vol Ratio",
    "debt_to_equity": "Debt/Equity",
    "ema_alignment": "EMA Alignment",
    "ema_stack": "EMA Stack",
    "eps_growth": "EPS Growth",
    "entry_zone": "Entry Zone",
    "entry_underlying_price": "Entry Price",
    "etf": "ETF",
    "extension_risk_score": "Extension Risk",
    "execution_note": "Execution Note",
    "failure_level": "Failure",
    "free_cash_flow_positive": "FCF Positive",
    "final_score": "Final",
    "final_signal": "Signal",
    "dollar_volume": "Dollar Vol",
    "inside_close_pct": "Inside Close",
    "heavyweight_detail": "Heavyweight Detail",
    "heavyweight_score": "Heavyweight",
    "income_suitability": "Income Fit",
    "invalidation_level": "Invalidation",
    "implied_volatility": "IV",
    "leadership_score": "Leadership",
    "leaps_suitability": "LEAPS Fit",
    "latest_return_pct": "Latest Return",
    "latest_volume": "Latest Vol",
    "latest_underlying_price": "Latest Price",
    "market_cap": "Market Cap",
    "missing": "Missing Rules",
    "mtf_score": "MTF",
    "mover_action": "Action",
    "no_trade_zone": "No-Trade Zone",
    "pattern_score": "Pattern Score",
    "pattern_type": "Pattern Type",
    "positive_20d_pct": "Positive 20D",
    "previous_rank": "Previous Rank",
    "previous_score": "Previous Score",
    "previous_posture": "Saved Posture",
    "previous_qx_action": "Saved QX Action",
    "previous_saved_status": "Saved Status",
    "previous_status": "Previous Status",
    "range_pct": "Range",
    "rank_change": "Rank Change",
    "rank_score": "Rank",
    "readiness_score": "Readiness Score",
    "readiness_label": "Status",
    "relative_20d": "Relative 20D",
    "relative_5d": "Relative 5D",
    "relative_60d": "Relative 60D",
    "relative_volume_20d": "RVOL 20D",
    "rectangle_score": "Rect Score",
    "rectangle_signal": "Rectangle",
    "resistance_distance_pct": "To Resistance",
    "retest_status": "Retest",
    "risk_reward": "Risk/Reward",
    "risk_score": "Risk Control",
    "rs_status": "RS",
    "rs_label": "RS",
    "rsi_status": "RSI",
    "rsi_14": "RSI 14",
    "rvol": "RVOL",
    "rule_score": "Rule",
    "setup_score": "Setup",
    "setup_status": "Status",
    "setup_state": "Setup State",
    "setup_type": "Setup Type",
    "sector_action": "Sector Action",
    "source": "Source",
    "stop_level": "Stop",
    "strike": "Strike",
    "spx_bias": "SPX Bias",
    "return_1d": "1D",
    "return_5d": "5D",
    "return_20d": "20D",
    "accumulation_ratio": "Accum Ratio",
    "accumulation_score": "Accum Score",
    "acceleration": "Acceleration",
    "avg_acceleration": "Avg Acceleration",
    "avg_leadership": "Avg Leadership",
    "avg_relative_20d": "Avg Relative 20D",
    "institutional_focus": "Institutional Focus",
    "rotation_status": "Rotation",
    "spy_return_20d": "SPY 20D",
    "support_slope_pct": "Support Slope",
    "volatility_context": "Volatility",
    "weekly_status": "Weekly",
    "underlying_quality": "Quality",
    "underlying_quality_score": "Quality Score",
    "quality_gate": "Quality Gate",
    "quality_breakdown": "Quality Breakdown",
    "quality_missing": "Missing Checks",
    "profit_margin": "Profit Margin",
    "priority": "Priority",
    "options_action": "Options",
    "options_quality": "Options Quality",
    "option_symbol": "Option",
    "option_type": "Type",
    "open_interest": "Open Interest",
    "price": "Price",
    "qx_action": "QX Action",
    "qx_ready_score": "QX Ready",
    "qx_rect_score": "QX Rect",
    "return_pct": "Return",
    "revenue_growth": "Revenue Growth",
    "roe": "ROE",
    "bias_ready_pct": "Bias Ready",
    "call_buy_score": "Call Buy",
    "no_trade_risk": "No-Trade Risk",
    "premium": "Premium",
    "put_buy_score": "Put Buy",
    "risk_tags": "Risk Tags",
    "saved_at": "Saved At",
    "saved_setup_score": "Saved Setup",
    "size": "Size",
    "timing_label": "Timing",
    "timing_read": "Timing Read",
    "timing_score": "Timing Score",
    "timing_state": "Timing State",
    "timing_trigger": "Timing Trigger",
    "target_1": "Target 1",
    "target_label": "Target Read",
    "target_upside_pct": "Target Upside",
    "tape_status": "Tape",
    "ticker": "Ticker",
    "trade_kind": "Kind",
    "trade_price": "Trade",
    "trade_posture": "Posture",
    "trade_side": "Side",
    "total_heavyweights": "Total",
    "trend_status": "Trend",
    "trend_label": "Trend",
    "trigger_level": "Trigger",
    "trigger_status": "Trigger",
    "upper_touches": "Upper Touches",
    "lower_touches": "Lower Touches",
    "vol_status": "Volume",
    "volume_label": "Volume",
}


DEFAULT_TABLE_COLUMNS = [
    "ticker",
    "symbol",
    "name",
    "sector",
    "industry",
    "readiness_label",
    "setup_state",
    "quality",
    "setup_status",
    "status",
    "group",
    "etf",
    "signal",
    "rotation_status",
    "sector_action",
    "final_score",
    "readiness_score",
    "rank_score",
    "current_rank",
    "previous_rank",
    "rank_change",
    "setup_score",
    "pattern_score",
    "breakout_setup_score",
    "risk_score",
    "trigger_level",
    "distance_to_trigger_pct",
    "close_location_20d",
    "mtf_score",
    "weekly_status",
    "support",
    "resistance",
    "breakout_level",
    "close",
    "prior_high",
    "prior_low",
    "prior_close",
    "latest_underlying_price",
    "latest_return_pct",
    "return_pct",
    "week_high",
    "week_low",
    "high_20d",
    "low_20d",
    "range_pct",
    "return_1d",
    "return_5d",
    "return_20d",
    "5d",
    "20d",
    "60d",
    "relative_5d",
    "relative_20d",
    "relative_60d",
    "acceleration",
    "above_sma20",
    "above_sma50",
    "above_sma50_pct",
    "above_sma200_pct",
    "positive_20d_pct",
    "breadth_score",
    "breadth_status",
    "breadth_source",
    "constituents_checked",
    "leadership_score",
    "extension_risk_score",
    "distance_from_sma20",
    "distance_from_sma50",
    "rsi_14",
    "heavyweight_score",
    "confirmation_status",
    "confirmed_heavyweights",
    "total_heavyweights",
    "heavyweight_detail",
    "distance_to_prior_high",
    "distance_to_prior_low",
    "location",
    "position",
    "distance_to_resistance",
    "resistance_distance_pct",
    "relative_volume_20d",
    "latest_volume",
    "avg_volume_20d",
    "dollar_volume",
    "market_cap",
    "close_location",
    "accumulation_ratio",
    "accumulation_score",
    "mover_score",
    "tape_status",
    "rectangle_signal",
    "rectangle_score",
    "options_quality",
    "missing",
    "note",
    "buyer_zone",
    "seller_zone",
    "chop_zone",
    "price",
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
    "upper_touches",
    "lower_touches",
    "bars_above_mid_pct",
    "vol_status",
    "accum_ratio",
    "rvol",
    "trend_status",
    "ema_stack",
    "breakout_status",
    "close_location",
    "qx_rect_score",
    "qx_action",
    "risk_reward",
]


def display_frame(
    frame: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    max_rows: int | None = None,
) -> pd.DataFrame:
    """Return a UI-safe, readable copy of a dataframe for Streamlit display."""
    if frame.empty:
        return frame

    if columns is not None:
        selected = _existing_columns(frame, columns)
        display = frame.loc[:, selected].copy()
    else:
        selected = _existing_columns(frame, DEFAULT_TABLE_COLUMNS)
        display = frame.loc[:, selected].copy() if selected else frame.copy()
    if max_rows is not None:
        display = display.head(max_rows)

    for column in display.columns:
        display[column] = display[column].map(lambda value, name=column: _format_value(name, value))

    display.columns = _unique_labels([_label(str(column)) for column in display.columns])
    return display


def format_timestamp(value: object, timezone: str = "America/New_York") -> str:
    """Display instants in explicit ET; legacy naive stored timestamps mean UTC.

    Calendar/session dates are labels, not midnight UTC instants.
    """
    if _is_missing(value):
        return "n/a"
    text = str(value).strip()
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.strftime("%b %d, %Y")
    try:
        return date.fromisoformat(text).strftime("%b %d, %Y")
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(ZoneInfo(timezone)).strftime("%b %d, %Y %I:%M %p %Z")


def _existing_columns(frame: pd.DataFrame, candidates: list[str]) -> list[str]:
    return [column for column in candidates if column in frame.columns]


def _format_value(column: str, value: Any) -> object:
    if isinstance(value, dict | list | tuple | set):
        return json.dumps(value, default=str)
    if _is_missing(value):
        return "n/a"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if column in {"created_at", "updated_at", "expires_at", "run_time", "saved_at",
                  "retrieved_at", "modified_at", "started_at", "finished_at"}:
        return format_timestamp(value)
    if isinstance(value, int | float):
        return _format_number(column, float(value))
    if column == "missing" and str(value).strip() == "":
        return "None"
    return value


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if value is pd.NA or value is pd.NaT:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    return False


def _format_number(column: str, value: float) -> str:
    if column in {
        "range_pct",
        "distance_to_resistance",
        "resistance_distance_pct",
        "distance_to_prior_high",
        "distance_to_prior_low",
        "inside_close_pct",
        "support_slope_pct",
        "resistance_slope_pct",
        "down_volume_ratio_10_to_20",
        "distance_from_sma20",
        "distance_from_sma50",
        "close_location",
    } or column.endswith("_pct"):
        return f"{value:.1%}"
    if column.startswith("relative_") and column != "relative_volume_20d":
        return f"{value:.1%}"
    if column in {
        "20d",
        "5d",
        "50d",
        "60d",
        "200d",
        "return_1d",
        "return_5d",
        "return_20d",
        "return_60d",
        "relative_5d",
        "relative_20d",
        "relative_60d",
        "acceleration",
        "avg_acceleration",
        "avg_relative_20d",
        "spy_return_20d",
        "realized_vol_20d",
    }:
        return f"{value:.1%}"
    if column in {"relative_volume_20d", "rvol", "rvol_20d"}:
        return f"{value:.2f}x"
    if column == "implied_volatility":
        return f"{value:.1%}" if value else "n/a"
    if column in {"avg_dollar_volume", "dollar_volume", "premium"}:
        if value >= 1_000_000_000:
            return f"${value / 1_000_000_000:.1f}B"
        return f"${value / 1_000_000:.0f}M" if value else "n/a"
    if column in {"latest_volume", "avg_volume_20d", "open_interest", "volume"}:
        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.1f}B"
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        return f"{value:,.0f}" if value else "n/a"
    if column == "market_cap":
        return f"${value / 1_000_000_000:.1f}B" if value else "n/a"
    if column in {"eps_growth", "revenue_growth", "roe", "debt_to_equity", "profit_margin"}:
        return f"{value:.1%}" if value else "n/a"
    if "score" in column or column in {
        "rank",
        "setup",
        "pattern",
        "readiness",
        "leadership",
        "call_buy_score",
        "put_buy_score",
        "no_trade_risk",
    }:
        return f"{value:.2f}"
    if column in {
        "support",
        "resistance",
        "breakout_level",
        "failure_level",
        "stop_level",
        "target_1",
        "price",
        "last",
        "latest_underlying_price",
        "entry_underlying_price",
        "close",
        "prior_high",
        "prior_low",
        "prior_close",
        "strike",
        "trade_price",
        "bid",
        "ask",
        "week_high",
        "week_low",
        "high_20d",
        "low_20d",
    }:
        return f"{value:.2f}"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _label(column: str) -> str:
    if column in COLUMN_LABELS:
        return COLUMN_LABELS[column]
    return column.replace("_", " ").title()


def _unique_labels(labels: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    unique: list[str] = []
    for label in labels:
        count = counts.get(label, 0)
        counts[label] = count + 1
        unique.append(label if count == 0 else f"{label} {count + 1}")
    return unique
