from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any

import pandas as pd

from qx.data.quotes import QuoteProvider
from qx.data.providers import MarketDataProvider
from qx.market.regime import MarketRegimeResult, analyze_market_regime
from qx.models.market import BarDataRequest
from qx.market.sessions import completed_mover_bars
from qx.market.futures_daily_evidence import daily_context_evidence, daily_series_evidence


@dataclass(frozen=True)
class FuturesContextRow:
    symbol: str
    name: str
    group: str
    close: float | None
    return_1d: float | None
    return_5d: float | None
    return_20d: float | None
    above_sma20: bool | None
    above_sma50: bool | None
    distance_to_prior_high: float | None
    distance_to_prior_low: float | None
    signal: str
    note: str


@dataclass(frozen=True)
class DecisionLevelSet:
    symbol: str
    name: str
    close: float | None
    prior_high: float | None
    prior_low: float | None
    prior_close: float | None
    week_high: float | None
    week_low: float | None
    high_20d: float | None
    low_20d: float | None
    distance_to_prior_high: float | None
    distance_to_prior_low: float | None
    location: str
    buyer_zone: str
    seller_zone: str
    chop_zone: str


@dataclass(frozen=True)
class TradingPlan:
    day_type: str
    primary_bias: str
    long_plan: str
    short_plan: str
    no_trade_zone: str
    risk_note: str
    confirmation_required: str


@dataclass(frozen=True)
class FuturesTimingRow:
    symbol: str
    name: str
    timing_state: str
    priority: int
    close: float | None
    trigger_level: float | None
    invalidation_level: float | None
    distance_to_trigger: float | None
    no_trade_zone: str
    execution_note: str
    risk_note: str


@dataclass(frozen=True)
class OpeningGapRead:
    prior_spx_close: float
    es_last: float | None
    es_reference: float | None
    es_change_points: float | None
    es_change_pct: float | None
    implied_spx_open: float | None
    implied_gap_points: float | None
    implied_gap_pct: float | None
    gap_type: str
    tone: str
    confidence: str
    data_source: str
    updated_at: str
    read: str


@dataclass(frozen=True)
class SpxDashboard:
    regime: MarketRegimeResult
    spy_close: float
    spy_prior_high: float
    spy_prior_low: float
    spy_prior_close: float
    spy_gap_pct: float
    spy_week_high: float
    spy_week_low: float
    spy_20d_high: float
    spy_20d_low: float
    spy_distance_to_prior_high: float
    spy_distance_to_prior_low: float
    spy_levels: DecisionLevelSet
    es_close: float | None
    # Legacy snapshot names: these are daily close-to-close returns, not overnight moves.
    es_overnight_move: float | None
    es_levels: DecisionLevelSet
    nq_close: float | None
    nq_overnight_move: float | None
    nq_prior_high: float | None
    nq_prior_low: float | None
    nq_levels: DecisionLevelSet
    vix_close: float | None
    futures_rows: list[FuturesContextRow]
    decision_level_sets: list[DecisionLevelSet]
    risk_appetite: str
    nq_bias: str
    confirmation_notes: list[str]
    volatility_context: str
    trend_bias: str
    trading_plan: TradingPlan
    timing_rows: list[FuturesTimingRow]
    buyer_zone: str
    seller_zone: str
    chop_zone: str
    decision_levels: list[str]
    action_plan: list[str]
    opening_gap: OpeningGapRead
    daily_evidence: dict[str, Any] = field(default_factory=dict)


def build_spx_dashboard(
    provider: MarketDataProvider,
    *,
    period: str = "2y",
    quote_provider: QuoteProvider | None = None,
    as_of: datetime | None = None,
) -> SpxDashboard:
    spy = provider.get_daily_bars(BarDataRequest(symbol="SPY", period=period))
    if as_of is not None:
        if not isinstance(spy.index, pd.DatetimeIndex):
            raise ValueError("SPY freshness requires dated bars")
        spy = completed_mover_bars(spy, as_of)
    regime = analyze_market_regime(provider, period=period, spy_bars=spy, as_of=as_of)
    es = _safe_bars(provider, "ES=F", period)
    nq = _safe_bars(provider, "NQ=F", period)
    checked_at = datetime.now(timezone.utc)
    evidence_rows = [
        daily_series_evidence(symbol, bars, checked_at=checked_at, as_of=as_of)
        for symbol, bars in (("ES=F", es), ("NQ=F", nq))
    ]
    daily_evidence = daily_context_evidence(evidence_rows, checked_at=checked_at)
    if evidence_rows[0]["status"] != "daily_reference":
        es = None
    if evidence_rows[1]["status"] != "daily_reference":
        nq = None
    vix = _safe_bars(provider, "^VIX", period)
    futures_rows = _futures_context(provider, period, preloaded={"ES=F": es, "NQ=F": nq})

    current = spy.iloc[-1]
    prior = spy.iloc[-2]
    week = spy.tail(5)
    month = spy.tail(20)
    spy_close = float(current["close"])
    spy_open = float(current["open"])
    prior_high = float(prior["high"])
    prior_low = float(prior["low"])
    prior_close = float(prior["close"])
    week_high = float(week["high"].max())
    week_low = float(week["low"].min())
    high_20d = float(month["high"].max())
    low_20d = float(month["low"].min())
    gap_pct = (spy_open / prior_close) - 1.0 if prior_close > 0 else 0.0
    spy_levels = _decision_level_set("SPY", "S&P 500 ETF", spy)

    es_close: float | None = None
    es_overnight_move: float | None = None
    if es is not None and len(es) >= 2:
        es_close = float(es["close"].iloc[-1])
        prior_es_close = float(es["close"].iloc[-2])
        es_overnight_move = (es_close / prior_es_close) - 1.0 if prior_es_close > 0 else None
    es_levels = _decision_level_set("ES=F", "S&P 500 Futures", es)

    nq_close: float | None = None
    nq_overnight_move: float | None = None
    nq_prior_high: float | None = None
    nq_prior_low: float | None = None
    if nq is not None and len(nq) >= 2:
        nq_close = float(nq["close"].iloc[-1])
        nq_prior = nq.iloc[-2]
        prior_nq_close = float(nq_prior["close"])
        nq_overnight_move = (nq_close / prior_nq_close) - 1.0 if prior_nq_close > 0 else None
        nq_prior_high = float(nq_prior["high"])
        nq_prior_low = float(nq_prior["low"])
    nq_levels = _decision_level_set("NQ=F", "Nasdaq 100 Futures", nq)

    vix_close = float(vix["close"].iloc[-1]) if vix is not None and not vix.empty else None
    volatility_context = _volatility_context(regime.realized_vol_20d, vix_close)
    trend_bias = _trend_bias(regime, spy_close, prior_high, prior_low)
    nq_bias = _nq_bias(nq_close, nq_prior_high, nq_prior_low, regime)
    risk_appetite = _risk_appetite(futures_rows, regime, vix_close)
    confirmation_notes = _confirmation_notes(
        es_overnight_move=es_overnight_move if daily_evidence["daily_labels_aligned"] else None,
        nq_overnight_move=nq_overnight_move if daily_evidence["daily_labels_aligned"] else None,
        futures_rows=futures_rows,
        risk_appetite=risk_appetite,
        nq_bias=nq_bias,
    )
    if not daily_evidence["daily_labels_aligned"]:
        confirmation_notes.append(
            "ES/NQ relative daily performance withheld: comparable daily bar labels are unavailable."
        )
    buyer_zone = f"Buyers need acceptance above {prior_high:.2f}"
    seller_zone = f"Sellers gain control below {prior_low:.2f}"
    chop_zone = f"Two-way chop between {prior_low:.2f} and {prior_high:.2f}"
    decision_level_sets = [spy_levels, es_levels, nq_levels]
    decision_levels = _decision_levels(decision_level_sets)
    trading_plan = _trading_plan(
        regime=regime,
        spy_levels=spy_levels,
        es_levels=es_levels,
        nq_levels=nq_levels,
        trend_bias=trend_bias,
        nq_bias=nq_bias,
        risk_appetite=risk_appetite,
        volatility_context=volatility_context,
        gap_pct=gap_pct,
    )
    timing_rows = _timing_rows(
        [spy_levels, es_levels, nq_levels],
        risk_appetite=risk_appetite,
        volatility_context=volatility_context,
    )
    action_plan = _action_plan(regime, trend_bias, nq_bias, risk_appetite, volatility_context, gap_pct)
    opening_gap = _opening_gap_read(
        prior_spx_close=spy_close,
        es_bars=es,
        quote_provider=quote_provider,
    )

    return SpxDashboard(
        regime=regime,
        spy_close=round(spy_close, 2),
        spy_prior_high=round(prior_high, 2),
        spy_prior_low=round(prior_low, 2),
        spy_prior_close=round(prior_close, 2),
        spy_gap_pct=round(gap_pct, 4),
        spy_week_high=round(week_high, 2),
        spy_week_low=round(week_low, 2),
        spy_20d_high=round(high_20d, 2),
        spy_20d_low=round(low_20d, 2),
        spy_distance_to_prior_high=round((spy_close / prior_high) - 1.0, 4),
        spy_distance_to_prior_low=round((spy_close / prior_low) - 1.0, 4),
        spy_levels=spy_levels,
        es_close=round(es_close, 2) if es_close is not None else None,
        es_overnight_move=round(es_overnight_move, 4) if es_overnight_move is not None else None,
        es_levels=es_levels,
        nq_close=round(nq_close, 2) if nq_close is not None else None,
        nq_overnight_move=round(nq_overnight_move, 4) if nq_overnight_move is not None else None,
        nq_prior_high=round(nq_prior_high, 2) if nq_prior_high is not None else None,
        nq_prior_low=round(nq_prior_low, 2) if nq_prior_low is not None else None,
        nq_levels=nq_levels,
        vix_close=round(vix_close, 2) if vix_close is not None else None,
        futures_rows=futures_rows,
        decision_level_sets=decision_level_sets,
        risk_appetite=risk_appetite,
        nq_bias=nq_bias,
        confirmation_notes=confirmation_notes,
        volatility_context=volatility_context,
        trend_bias=trend_bias,
        trading_plan=trading_plan,
        timing_rows=timing_rows,
        buyer_zone=buyer_zone,
        seller_zone=seller_zone,
        chop_zone=chop_zone,
        decision_levels=decision_levels,
        action_plan=action_plan,
        opening_gap=opening_gap,
        daily_evidence=daily_evidence,
    )


def _safe_bars(provider: MarketDataProvider, symbol: str, period: str) -> pd.DataFrame | None:
    try:
        return provider.get_daily_bars(BarDataRequest(symbol=symbol, period=period))
    except Exception:
        return None


FUTURES_MARKETS: tuple[tuple[str, str, str], ...] = (
    ("ES=F", "S&P 500", "Equity Index"),
    ("NQ=F", "Nasdaq 100", "Equity Index"),
    ("YM=F", "Dow", "Equity Index"),
    ("RTY=F", "Russell 2000", "Equity Index"),
    ("ZN=F", "10Y Note", "Rates"),
    ("ZB=F", "30Y Bond", "Rates"),
    ("DX-Y.NYB", "US Dollar", "Macro"),
    ("CL=F", "Crude Oil", "Commodity"),
    ("GC=F", "Gold", "Commodity"),
)


def futures_context_frame(rows: list[FuturesContextRow]) -> pd.DataFrame:
    return pd.DataFrame([row.__dict__ for row in rows])


def decision_levels_frame(levels: list[DecisionLevelSet]) -> pd.DataFrame:
    return pd.DataFrame([level.__dict__ for level in levels])


def trading_plan_frame(plan: TradingPlan) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"area": "Day Type", "plan": plan.day_type},
            {"area": "Primary Bias", "plan": plan.primary_bias},
            {"area": "Long Plan", "plan": plan.long_plan},
            {"area": "Short Plan", "plan": plan.short_plan},
            {"area": "No Trade Zone", "plan": plan.no_trade_zone},
            {"area": "Risk Note", "plan": plan.risk_note},
            {"area": "Confirmation", "plan": plan.confirmation_required},
        ]
    )


def futures_timing_frame(rows: list[FuturesTimingRow]) -> pd.DataFrame:
    return pd.DataFrame([row.__dict__ for row in rows])


def _futures_context(
    provider: MarketDataProvider,
    period: str,
    *,
    preloaded: dict[str, pd.DataFrame | None] | None = None,
) -> list[FuturesContextRow]:
    rows_by_symbol: dict[str, FuturesContextRow] = {}
    histories = preloaded if preloaded is not None else {}

    def load_market(symbol: str, name: str, group: str) -> FuturesContextRow:
        # Reuse failed reads too: one build must not mix separate ES/NQ observations.
        bars = histories[symbol] if symbol in histories else _safe_bars(provider, symbol, period)
        return _futures_row(symbol, name, group, bars)

    with ThreadPoolExecutor(max_workers=min(8, len(FUTURES_MARKETS))) as executor:
        future_by_symbol = {
            executor.submit(load_market, symbol, name, group): symbol
            for symbol, name, group in FUTURES_MARKETS
        }
        for future in as_completed(future_by_symbol):
            symbol = future_by_symbol[future]
            rows_by_symbol[symbol] = future.result()

    return [rows_by_symbol[symbol] for symbol, _, _ in FUTURES_MARKETS]


def _decision_level_set(symbol: str, name: str, bars: pd.DataFrame | None) -> DecisionLevelSet:
    if bars is None or len(bars) < 20:
        return DecisionLevelSet(
            symbol=symbol,
            name=name,
            close=None,
            prior_high=None,
            prior_low=None,
            prior_close=None,
            week_high=None,
            week_low=None,
            high_20d=None,
            low_20d=None,
            distance_to_prior_high=None,
            distance_to_prior_low=None,
            location="No Data",
            buyer_zone="No data",
            seller_zone="No data",
            chop_zone="No data",
        )

    current = bars.iloc[-1]
    prior = bars.iloc[-2]
    close = float(current["close"])
    prior_high = float(prior["high"])
    prior_low = float(prior["low"])
    prior_close = float(prior["close"])
    week = bars.tail(5)
    month = bars.tail(20)
    distance_to_prior_high = (close / prior_high) - 1.0 if prior_high > 0 else None
    distance_to_prior_low = (close / prior_low) - 1.0 if prior_low > 0 else None
    location = _price_location(close, prior_high, prior_low)

    return DecisionLevelSet(
        symbol=symbol,
        name=name,
        close=round(close, 2),
        prior_high=round(prior_high, 2),
        prior_low=round(prior_low, 2),
        prior_close=round(prior_close, 2),
        week_high=round(float(week["high"].max()), 2),
        week_low=round(float(week["low"].min()), 2),
        high_20d=round(float(month["high"].max()), 2),
        low_20d=round(float(month["low"].min()), 2),
        distance_to_prior_high=round(distance_to_prior_high, 4) if distance_to_prior_high is not None else None,
        distance_to_prior_low=round(distance_to_prior_low, 4) if distance_to_prior_low is not None else None,
        location=location,
        buyer_zone=f"{name} buyers need acceptance above {prior_high:.2f}",
        seller_zone=f"{name} sellers gain control below {prior_low:.2f}",
        chop_zone=f"{name} two-way chop between {prior_low:.2f} and {prior_high:.2f}",
    )


def _price_location(close: float, prior_high: float, prior_low: float) -> str:
    if close > prior_high:
        return "Above Prior High"
    if close < prior_low:
        return "Below Prior Low"
    midpoint = (prior_high + prior_low) / 2
    if close >= midpoint:
        return "Inside Range - Upper Half"
    return "Inside Range - Lower Half"


def _futures_row(
    symbol: str,
    name: str,
    group: str,
    bars: pd.DataFrame | None,
) -> FuturesContextRow:
    if bars is None or len(bars) < 60:
        return FuturesContextRow(
            symbol=symbol,
            name=name,
            group=group,
            close=None,
            return_1d=None,
            return_5d=None,
            return_20d=None,
            above_sma20=None,
            above_sma50=None,
            distance_to_prior_high=None,
            distance_to_prior_low=None,
            signal="No Data",
            note="market data unavailable",
        )
    close = float(bars["close"].iloc[-1])
    prior = bars.iloc[-2]
    prior_high = float(prior["high"])
    prior_low = float(prior["low"])
    sma20 = float(bars["close"].rolling(20).mean().dropna().iloc[-1])
    sma50 = float(bars["close"].rolling(50).mean().dropna().iloc[-1])
    return_1d = _return_over_bars(bars, 1)
    return_5d = _return_over_bars(bars, 5)
    return_20d = _return_over_bars(bars, 20)
    above_sma20 = close > sma20
    above_sma50 = close > sma50
    distance_to_high = (close / prior_high) - 1.0 if prior_high > 0 else None
    distance_to_low = (close / prior_low) - 1.0 if prior_low > 0 else None
    signal = _futures_signal(group, return_1d, return_5d, above_sma20, above_sma50)
    return FuturesContextRow(
        symbol=symbol,
        name=name,
        group=group,
        close=round(close, 2),
        return_1d=round(return_1d, 4),
        return_5d=round(return_5d, 4),
        return_20d=round(return_20d, 4),
        above_sma20=above_sma20,
        above_sma50=above_sma50,
        distance_to_prior_high=round(distance_to_high, 4) if distance_to_high is not None else None,
        distance_to_prior_low=round(distance_to_low, 4) if distance_to_low is not None else None,
        signal=signal,
        note=_futures_note(name, group, signal, return_1d, above_sma20, above_sma50),
    )


def _futures_signal(
    group: str,
    return_1d: float,
    return_5d: float,
    above_sma20: bool,
    above_sma50: bool,
) -> str:
    trend_points = int(return_1d > 0) + int(return_5d > 0) + int(above_sma20) + int(above_sma50)
    if group == "Rates":
        if trend_points >= 3:
            return "Yields Down / Growth Support"
        if trend_points <= 1:
            return "Yields Up / Pressure"
        return "Rates Mixed"
    if trend_points >= 3:
        return "Risk-On"
    if trend_points <= 1:
        return "Risk-Off"
    return "Mixed"


def _futures_note(
    name: str,
    group: str,
    signal: str,
    return_1d: float,
    above_sma20: bool,
    above_sma50: bool,
) -> str:
    direction = "green" if return_1d > 0 else "red"
    trend = "above 20/50" if above_sma20 and above_sma50 else "below a key average"
    if group == "Rates":
        return f"{name} is {direction}; bond strength can support growth if it persists."
    if group == "Macro" and signal == "Risk-On":
        return f"{name} firming; watch for pressure on multinationals and commodities."
    return f"{name} is {direction} and {trend}."


def _trend_bias(
    regime: MarketRegimeResult,
    spy_close: float,
    prior_high: float,
    prior_low: float,
) -> str:
    if regime.label in {"Risk On", "Constructive"} and spy_close >= prior_high:
        return "Bullish Breakout"
    if regime.label == "Risk Off" and spy_close <= prior_low:
        return "Bearish Breakdown"
    if regime.label in {"Risk On", "Constructive"}:
        return "Bullish Above Support"
    if regime.label == "Risk Off":
        return "Defensive"
    return "Two-Way / Choppy"


def _nq_bias(
    nq_close: float | None,
    nq_prior_high: float | None,
    nq_prior_low: float | None,
    regime: MarketRegimeResult,
) -> str:
    if nq_close is None or nq_prior_high is None or nq_prior_low is None:
        return "NQ Data Unavailable"
    if regime.label in {"Risk On", "Constructive"} and nq_close >= nq_prior_high:
        return "NQ Bullish Breakout"
    if regime.label == "Risk Off" and nq_close <= nq_prior_low:
        return "NQ Bearish Breakdown"
    if nq_close > nq_prior_high:
        return "NQ Above Prior High"
    if nq_close < nq_prior_low:
        return "NQ Below Prior Low"
    return "NQ Inside Prior Range"


def _risk_appetite(
    rows: list[FuturesContextRow],
    regime: MarketRegimeResult,
    vix_close: float | None,
) -> str:
    equity_rows = [row for row in rows if row.group == "Equity Index"]
    risk_on_count = sum(row.signal == "Risk-On" for row in equity_rows)
    risk_off_count = sum(row.signal == "Risk-Off" for row in equity_rows)
    vix_pressure = vix_close is not None and vix_close >= 25
    if risk_on_count >= 3 and regime.is_constructive and not vix_pressure:
        return "Risk-On Confirmed"
    if risk_off_count >= 2 or vix_pressure or regime.risk_level == "High":
        return "Defensive / Risk-Off"
    return "Mixed / Wait for Confirmation"


def _confirmation_notes(
    *,
    es_overnight_move: float | None,
    nq_overnight_move: float | None,
    futures_rows: list[FuturesContextRow],
    risk_appetite: str,
    nq_bias: str,
) -> list[str]:
    notes = [f"Risk appetite: {risk_appetite}.", f"NQ context: {nq_bias}."]
    if es_overnight_move is not None and nq_overnight_move is not None:
        spread = nq_overnight_move - es_overnight_move
        if spread > 0.0025:
            notes.append("NQ's daily close-to-close return exceeds ES by more than 0.25 percentage points.")
        elif spread < -0.0025:
            notes.append("NQ's daily close-to-close return trails ES by more than 0.25 percentage points.")
        else:
            notes.append("ES/NQ daily close-to-close returns are within 0.25 percentage points.")
    rates = next((row for row in futures_rows if row.symbol == "ZN=F"), None)
    dollar = next((row for row in futures_rows if row.symbol == "DX-Y.NYB"), None)
    if rates and rates.signal == "Yields Up / Pressure":
        notes.append("Rates are pressuring growth; demand stronger confirmation on NQ longs.")
    if dollar and dollar.signal == "Risk-On":
        notes.append("Dollar strength is a macro headwind to broad risk appetite.")
    return notes


def _volatility_context(realized_vol_20d: float, vix_close: float | None) -> str:
    if realized_vol_20d >= 0.25 or (vix_close is not None and vix_close >= 25):
        return "Elevated"
    if realized_vol_20d <= 0.12 and (vix_close is None or vix_close < 18):
        return "Calm"
    return "Normal"


def _decision_levels(level_sets: list[DecisionLevelSet]) -> list[str]:
    levels: list[str] = []
    for level in level_sets:
        if level.close is None:
            levels.append(f"{level.name}: data unavailable.")
            continue
        levels.append(
            f"{level.name}: {level.location}; prior range {level.prior_low:.2f} to {level.prior_high:.2f}."
        )
        levels.append(f"{level.name}: 5-day range {level.week_low:.2f} to {level.week_high:.2f}.")
        levels.append(f"{level.name}: 20-day range {level.low_20d:.2f} to {level.high_20d:.2f}.")
    return levels


def _trading_plan(
    *,
    regime: MarketRegimeResult,
    spy_levels: DecisionLevelSet,
    es_levels: DecisionLevelSet,
    nq_levels: DecisionLevelSet,
    trend_bias: str,
    nq_bias: str,
    risk_appetite: str,
    volatility_context: str,
    gap_pct: float,
) -> TradingPlan:
    day_type = _day_type(trend_bias, nq_bias, risk_appetite, volatility_context, gap_pct)
    primary_bias = _primary_bias(day_type, regime, risk_appetite)
    reference = es_levels if es_levels.close is not None else spy_levels
    leader = "NQ leading" if "Bullish" in nq_bias or "Above" in nq_bias else "NQ not leading"
    long_plan = _long_plan(day_type, reference, leader)
    short_plan = _short_plan(day_type, reference, volatility_context)
    no_trade_zone = reference.chop_zone if reference.close is not None else "No trade zone unavailable until futures data loads."
    risk_note = _risk_note(regime, volatility_context, gap_pct)
    confirmation_required = _confirmation_required(day_type, reference, nq_levels)
    return TradingPlan(
        day_type=day_type,
        primary_bias=primary_bias,
        long_plan=long_plan,
        short_plan=short_plan,
        no_trade_zone=no_trade_zone,
        risk_note=risk_note,
        confirmation_required=confirmation_required,
    )


def _day_type(
    trend_bias: str,
    nq_bias: str,
    risk_appetite: str,
    volatility_context: str,
    gap_pct: float,
) -> str:
    if "Defensive" in risk_appetite or "Bearish" in trend_bias:
        return "Defense First"
    if volatility_context == "Elevated":
        return "Wide Range / Reduce Size"
    if abs(gap_pct) >= 0.005:
        return "Gap Acceptance Day"
    if "Risk-On" in risk_appetite and "Bullish" in trend_bias and ("Bullish" in nq_bias or "Above" in nq_bias):
        return "Trend Continuation"
    if "Mixed" in risk_appetite:
        return "Confirmation Required"
    return "Two-Way Range"


def _primary_bias(day_type: str, regime: MarketRegimeResult, risk_appetite: str) -> str:
    if day_type == "Trend Continuation":
        return "Long bias while ES/SPY hold above prior-day support."
    if day_type == "Defense First":
        return "Short or cash bias until buyers reclaim prior-day high."
    if day_type == "Gap Acceptance Day":
        return "Trade in the direction of accepted gap only after the first range resolves."
    if day_type == "Wide Range / Reduce Size":
        return "Directional trades require wider stops and smaller size."
    if "Risk-On" in risk_appetite and regime.is_constructive:
        return "Constructive, but wait for ES and NQ confirmation."
    return "Neutral until price exits the prior-day range."


def _long_plan(day_type: str, reference: DecisionLevelSet, leader: str) -> str:
    if reference.close is None or reference.prior_high is None or reference.prior_low is None:
        return "Wait for futures data before taking directional longs."
    if day_type == "Defense First":
        return f"Only consider longs after reclaiming {reference.prior_high:.2f} and holding above it."
    if day_type == "Trend Continuation":
        return f"Favor pullbacks that hold {reference.prior_high:.2f} or reclaim it quickly; {leader}."
    return f"Longs need acceptance above {reference.prior_high:.2f}; avoid buying the middle of the range."


def _short_plan(day_type: str, reference: DecisionLevelSet, volatility_context: str) -> str:
    if reference.close is None or reference.prior_low is None:
        return "Wait for futures data before taking directional shorts."
    if day_type == "Trend Continuation":
        return f"Shorts are lower priority unless price loses {reference.prior_low:.2f} with failed reclaim."
    if day_type == "Defense First":
        return f"Short bounces that fail below {reference.prior_low:.2f} or reject prior range reclaim."
    if volatility_context == "Elevated":
        return f"Shorts can work below {reference.prior_low:.2f}, but use smaller size due to volatility."
    return f"Shorts need clean acceptance below {reference.prior_low:.2f}; avoid fading inside range."


def _risk_note(regime: MarketRegimeResult, volatility_context: str, gap_pct: float) -> str:
    notes: list[str] = []
    if regime.risk_level == "High":
        notes.append("market regime risk is high")
    if volatility_context == "Elevated":
        notes.append("volatility is elevated")
    if abs(gap_pct) >= 0.005:
        notes.append("opening gap is meaningful")
    if not notes:
        return "Normal risk controls are acceptable; still define invalidation before entry."
    return "Reduce size because " + ", ".join(notes) + "."


def _confirmation_required(
    day_type: str,
    reference: DecisionLevelSet,
    nq_levels: DecisionLevelSet,
) -> str:
    if reference.close is None:
        return "Need ES/SPY data before confirmation can be evaluated."
    if day_type == "Trend Continuation" and nq_levels.close is not None and nq_levels.prior_high is not None:
        return f"Best long confirmation is ES holding its prior high with NQ above {nq_levels.prior_high:.2f}."
    if day_type == "Defense First":
        return "Best short confirmation is failed reclaim of prior low/high after an attempted bounce."
    return "Wait for acceptance outside prior-day range; avoid acting on first touch alone."


def _timing_rows(
    levels: list[DecisionLevelSet],
    *,
    risk_appetite: str,
    volatility_context: str,
) -> list[FuturesTimingRow]:
    return [
        _timing_row(level, risk_appetite=risk_appetite, volatility_context=volatility_context)
        for level in levels
    ]


def _timing_row(
    level: DecisionLevelSet,
    *,
    risk_appetite: str,
    volatility_context: str,
) -> FuturesTimingRow:
    if level.close is None or level.prior_high is None or level.prior_low is None:
        return FuturesTimingRow(
            symbol=level.symbol,
            name=level.name,
            timing_state="No Data",
            priority=0,
            close=None,
            trigger_level=None,
            invalidation_level=None,
            distance_to_trigger=None,
            no_trade_zone=level.chop_zone,
            execution_note="Wait for futures data before building an intraday plan.",
            risk_note="No risk read available.",
        )

    bullish_context = "Risk-On" in risk_appetite and volatility_context != "Elevated"
    defensive_context = "Defensive" in risk_appetite or volatility_context == "Elevated"
    if level.location == "Above Prior High":
        timing_state = "Long Trigger Active" if bullish_context else "Extended Long - Confirm"
        trigger_level = level.prior_high
        invalidation_level = level.prior_high
        distance_to_trigger = level.distance_to_prior_high
        priority = 5 if bullish_context else 3
        execution_note = f"Buyers are above {level.prior_high:.2f}; prefer pullback holds over chasing extension."
    elif level.location == "Below Prior Low":
        timing_state = "Short Trigger Active" if defensive_context else "Failed Support - Wait"
        trigger_level = level.prior_low
        invalidation_level = level.prior_low
        distance_to_trigger = level.distance_to_prior_low
        priority = 5 if defensive_context else 2
        execution_note = f"Sellers are below {level.prior_low:.2f}; longs need reclaim before action."
    elif level.location == "Inside Range - Upper Half":
        timing_state = "Long Setup Building" if bullish_context else "Upper Range Chop"
        trigger_level = level.prior_high
        invalidation_level = level.prior_low
        distance_to_trigger = level.distance_to_prior_high
        priority = 4 if bullish_context else 2
        execution_note = f"Wait for acceptance above {level.prior_high:.2f}; avoid midpoint entries."
    else:
        timing_state = "Short Setup Building" if defensive_context else "Lower Range Chop"
        trigger_level = level.prior_low
        invalidation_level = level.prior_high
        distance_to_trigger = level.distance_to_prior_low
        priority = 4 if defensive_context else 1
        execution_note = f"Wait for acceptance below {level.prior_low:.2f} or reclaim back above midpoint."

    risk_note = (
        "Reduce size and require confirmation because volatility is elevated."
        if volatility_context == "Elevated"
        else "Use prior range as the hard invalidation map."
    )
    return FuturesTimingRow(
        symbol=level.symbol,
        name=level.name,
        timing_state=timing_state,
        priority=priority,
        close=level.close,
        trigger_level=round(trigger_level, 2) if trigger_level is not None else None,
        invalidation_level=round(invalidation_level, 2) if invalidation_level is not None else None,
        distance_to_trigger=round(distance_to_trigger, 4) if distance_to_trigger is not None else None,
        no_trade_zone=level.chop_zone,
        execution_note=execution_note,
        risk_note=risk_note,
    )


def _action_plan(
    regime: MarketRegimeResult,
    trend_bias: str,
    nq_bias: str,
    risk_appetite: str,
    volatility_context: str,
    gap_pct: float,
) -> list[str]:
    plan: list[str] = []
    if "Risk-On" in risk_appetite and "Bullish" in trend_bias:
        plan.append("Favor long setups above prior-day low; avoid chasing if price is extended above prior high.")
    elif "Bearish" in trend_bias or trend_bias == "Defensive":
        plan.append("Favor defense first; require reclaim of prior-day high before leaning long.")
    else:
        plan.append("Expect two-way trade; use prior-day high/low as decision boundaries.")
    if "NQ Bullish" in nq_bias:
        plan.append("For NQ, prioritize pullbacks that hold prior high or VWAP after the open.")
    elif "NQ Below" in nq_bias or "NQ Bearish" in nq_bias:
        plan.append("For NQ, avoid early longs until buyers reclaim the prior low/high decision area.")
    if volatility_context == "Elevated":
        plan.append("Use smaller size because realized volatility is elevated.")
    if risk_appetite == "Mixed / Wait for Confirmation":
        plan.append("Require ES and NQ confirmation before sizing directional SPX trades.")
    if abs(gap_pct) >= 0.005:
        plan.append("Market has a meaningful opening gap; wait for acceptance above/below prior range.")
    if regime.risk_level == "Low":
        plan.append("Scanner breakouts have better broad-market support today.")
    return plan


def _return_over_bars(bars: pd.DataFrame, bars_back: int) -> float:
    if len(bars) <= bars_back:
        return 0.0
    current = float(bars["close"].iloc[-1])
    previous = float(bars["close"].iloc[-bars_back - 1])
    return (current / previous) - 1.0 if previous > 0 else 0.0


def _opening_gap_read(
    *,
    prior_spx_close: float,
    es_bars: pd.DataFrame | None,
    quote_provider: QuoteProvider | None,
) -> OpeningGapRead:
    es_last: float | None = None
    quote_available = False
    data_source = "ES daily bars"
    updated_at = "cached bars"
    if quote_provider is not None:
        try:
            quote = quote_provider.get_quote("ES=F")
            if quote.last is not None and math.isfinite(quote.last) and quote.last > 0:
                es_last = float(quote.last)
                quote_available = True
                data_source = quote.provider
                updated_at = quote.timestamp.isoformat() if quote.timestamp else "quote timestamp unavailable"
        except Exception:
            es_last = None

    if es_last is None and es_bars is not None and not es_bars.empty:
        es_last = float(es_bars["close"].iloc[-1])

    # A quote is compared with the latest cached close; cached bars compare two closes.
    es_reference = _es_reference_close(es_bars, quote_available=quote_available)
    if (es_last is None or es_reference is None or not math.isfinite(es_last)
            or not math.isfinite(es_reference) or es_last <= 0 or es_reference <= 0
            or not math.isfinite(prior_spx_close) or prior_spx_close <= 0):
        return OpeningGapRead(
            prior_spx_close=round(prior_spx_close, 2),
            es_last=round(es_last, 2) if es_last is not None else None,
            es_reference=round(es_reference, 2) if es_reference is not None else None,
            es_change_points=None,
            es_change_pct=None,
            implied_spx_open=None,
            implied_gap_points=None,
            implied_gap_pct=None,
            gap_type="Unavailable",
            tone="neutral",
            confidence="Low",
            data_source=data_source,
            updated_at=updated_at,
            read="Opening read unavailable until ES quote and prior ES reference are available.",
        )

    es_change_points = es_last - es_reference
    es_change_pct = es_change_points / es_reference
    # Daily futures closes are not synchronized with the SPY cash close. Do not
    # turn this comparison into an opening forecast or pass it to AI as a fact.
    return OpeningGapRead(
        prior_spx_close=round(prior_spx_close, 2),
        es_last=round(es_last, 2),
        es_reference=round(es_reference, 2),
        es_change_points=round(es_change_points, 2),
        es_change_pct=round(es_change_pct, 4),
        implied_spx_open=None,
        implied_gap_points=None,
        implied_gap_pct=None,
        gap_type="Unavailable",
        tone="neutral",
        confidence="Unverified",
        data_source=data_source,
        updated_at=updated_at,
        read="ES comparison only, not an overnight move or opening forecast. "
        "A synchronized cash-close reference, verified quote freshness and contract continuity are unavailable.",
    )


def _es_reference_close(es_bars: pd.DataFrame | None, *, quote_available: bool = False) -> float | None:
    if es_bars is None or es_bars.empty:
        return None
    if quote_available:
        return float(es_bars["close"].iloc[-1])
    if len(es_bars) >= 2:
        return float(es_bars["close"].iloc[-2])
    return None
