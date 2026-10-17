"""Institutional Smart Money Concepts (SMC) & Market Structure Engine (Phase 4).

Translates ThinkScript SMC_Complete_Suite_v3_1 into Python with strict 0-lookahead
pivot confirmation, explicit structural state machine (NEUTRAL -> BULLISH/BEARISH),
prior-state event classification (BOS vs CHoCH vs INITIAL_BREAK), break confirmation mode,
protected swing tracking, duplicate event prevention, and deterministic Phase 4 Order Block Engine.
"""

from typing import Any, Dict, List, Optional, Set
import pandas as pd
import numpy as np
from pydantic import BaseModel, Field, model_validator
from qx.config.rules_config import load_rules_config


class OrderBlock(BaseModel):
    order_block_id: str
    symbol: str = "XLK"
    timeframe: str = "5m"
    direction: str  # "BULLISH_ORDER_BLOCK" or "BEARISH_ORDER_BLOCK"
    state: str = "VALIDATED"  # "CANDIDATE", "VALIDATED", "MITIGATED", "INVALIDATED", "EXPIRED"

    candidate_bar_index: int
    candidate_timestamp: str
    candidate_available_at: str = ""
    candidate_knowledge_timestamp: str = ""

    zone_low: float
    zone_high: float
    proximal_price: float
    distal_price: float

    validation_event_id: Optional[str] = None
    validation_event_type: Optional[str] = None
    validation_bar_index: Optional[int] = None
    validated_at: Optional[str] = None
    knowledge_timestamp: Optional[str] = None

    source_leg_start_pivot_id: Optional[str] = None
    source_leg_end_event_id: Optional[str] = None

    displacement_atr: float = 0.0
    body_multiplier: float = 0.0

    fvg_created: bool = False
    fvg_id: Optional[str] = None

    mitigation_count: int = 0
    first_mitigation_timestamp: Optional[str] = None
    last_mitigation_timestamp: Optional[str] = None
    mitigation_depth_pct: float = 0.0

    invalidation_timestamp: Optional[str] = None
    expiration_timestamp: Optional[str] = None

    candidate_age_bars: int = 0
    validation_age_bars: int = 0
    age_bars: int = 0

    config_version: str = "research_v1"
    engine_version: str = "v4.1.0"

    evidence_ladder: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _parse_legacy_kwargs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            block_type = data.get("block_type")
            if block_type and "direction" not in data:
                data["direction"] = "BULLISH_ORDER_BLOCK" if "DEMAND" in str(block_type).upper() else "BEARISH_ORDER_BLOCK"

            bar_idx = data.get("bar_index")
            if bar_idx is not None and "candidate_bar_index" not in data:
                data["candidate_bar_index"] = int(bar_idx)

            top_p = data.get("top_price")
            bot_p = data.get("bottom_price")
            if top_p is not None and "zone_high" not in data:
                data["zone_high"] = float(top_p)
            if bot_p is not None and "zone_low" not in data:
                data["zone_low"] = float(bot_p)

            if "proximal_price" not in data and top_p is not None and bot_p is not None:
                is_bullish = "BULLISH" in data.get("direction", "BULLISH_ORDER_BLOCK")
                data["proximal_price"] = float(top_p) if is_bullish else float(bot_p)
                data["distal_price"] = float(bot_p) if is_bullish else float(top_p)

            if "candidate_timestamp" not in data:
                data["candidate_timestamp"] = "legacy"
            if "candidate_available_at" not in data or not data.get("candidate_available_at"):
                data["candidate_available_at"] = data.get("candidate_knowledge_timestamp", data["candidate_timestamp"])
            if "candidate_knowledge_timestamp" not in data or not data.get("candidate_knowledge_timestamp"):
                data["candidate_knowledge_timestamp"] = data["candidate_available_at"]
            if "order_block_id" not in data:
                data["order_block_id"] = f"OB_LEGACY_{data.get('candidate_bar_index', 0)}"

            if data.get("is_mitigated") and "state" not in data:
                data["state"] = "MITIGATED"
                data["mitigation_count"] = 1
        return data

    @property
    def block_type(self) -> str:
        return "DEMAND_OB" if "BULLISH" in self.direction else "SUPPLY_OB"

    @property
    def top_price(self) -> float:
        return self.zone_high

    @property
    def bottom_price(self) -> float:
        return self.zone_low

    @property
    def bar_index(self) -> int:
        return self.candidate_bar_index

    @property
    def is_mitigated(self) -> bool:
        return self.mitigation_count > 0 or self.state in ("MITIGATED", "INVALIDATED", "EXPIRED")


class LiquidityPool(BaseModel):
    pool_id: str = ""
    pool_type: str  # "EQH" or "EQL"
    price: float
    tolerance_pct: float = 0.075
    source_pivot_ids: List[str] = Field(default_factory=list)
    knowledge_timestamp: str = ""


class StructuralPivot(BaseModel):
    pivot_id: str
    pivot_type: str  # "HIGH" or "LOW"
    pivot_price: float
    pivot_timestamp: str  # timestamp of actual swing bar
    confirmation_timestamp: str  # timestamp when pivot was confirmed (bar_index + half_ext)
    knowledge_timestamp: str  # timestamp when system can use pivot (research_v1 = confirmation_timestamp)
    classification: str = "EXTERNAL"  # "EXTERNAL", "INTERNAL", "UNCLASSIFIED"
    timeframe: str = "5m"
    confirmed: bool = True
    bar_index: int
    confirmation_bar_index: int


class ProtectedSwing(BaseModel):
    role: str  # "ACTIVE_HIGH", "ACTIVE_LOW", "PROTECTED_HIGH", "PROTECTED_LOW"
    swing_type: str = ""  # alias for backwards compatibility
    price: float
    pivot_id: str
    pivot_timestamp: str
    knowledge_timestamp: str
    promoted_at: str
    promoted_by_event_id: Optional[str] = None
    selection_reason: str = "PULLBACK_BEFORE_BOS"  # "PULLBACK_BEFORE_BOS", "RALLY_BEFORE_BOS", "INITIAL_BREAK_BASE", "CHOCH_TRANSITION", "STRUCTURAL_FALLBACK_UNAVAILABLE"
    source_leg_start_pivot_id: Optional[str] = None
    source_leg_end_event_id: Optional[str] = None
    timeframe: str = "5m"
    bar_index: int
    confirmation_bar_index: int


class StructureEvent(BaseModel):
    event_id: str
    symbol: str
    timeframe: str = "5m"
    event_type: str  # "BULLISH_BOS", "BEARISH_BOS", "BULLISH_CHOCH", "BEARISH_CHOCH", "BULLISH_INITIAL_BREAK", "BEARISH_INITIAL_BREAK"
    direction: str  # "BULLISH" or "BEARISH"
    level_broken: float
    event_timestamp: str
    knowledge_timestamp: str
    previous_structure_state: str  # "NEUTRAL", "BULLISH", "BEARISH"
    new_structure_state: str  # "BULLISH", "BEARISH"
    source_pivot_id: str
    confirmation_method: str = "CLOSE"  # "CLOSE", "WICK", "CLOSE_WITH_ATR_BUFFER"
    config_version: str = "research_v1"
    engine_version: str = "v3.1.0"


class SMCAnalysisResult(BaseModel):
    regime: str  # "NEUTRAL", "BULLISH", or "BEARISH"
    latest_bos: Optional[str] = None
    latest_choch: Optional[str] = None
    latest_event: Optional[StructureEvent] = None
    events: List[StructureEvent] = Field(default_factory=list)
    confirmed_pivots: List[StructuralPivot] = Field(default_factory=list)
    protected_low: Optional[ProtectedSwing] = None
    protected_high: Optional[ProtectedSwing] = None
    active_high: Optional[ProtectedSwing] = None
    active_low: Optional[ProtectedSwing] = None
    demand_ob: Optional[OrderBlock] = None
    supply_ob: Optional[OrderBlock] = None
    order_blocks: List[OrderBlock] = Field(default_factory=list)
    liquidity_pools: List[LiquidityPool] = Field(default_factory=list)
    structure_score: float = Field(ge=0.0, le=100.0)


def get_max_leg_lookback_bars(timeframe: str = "5m") -> int:
    """Load max_leg_lookback_bars from rules configuration for the specified timeframe."""
    cfg = load_rules_config()
    lookback_dict = cfg.structure.protected_swing.get("max_leg_lookback_bars", {})
    return lookback_dict.get(timeframe, 25)


def find_qualified_pullback_low(
    knowable_low_pivots: List[StructuralPivot],
    leg_start_bar: int,
    break_bar: int,
    evaluation_bar: int,
    max_lookback_bars: int = 25,
) -> Optional[StructuralPivot]:
    """Find qualified EXTERNAL low pivot formed during the pullback leg between leg_start_bar and break_bar."""
    candidates = [
        p for p in knowable_low_pivots
        if p.classification == "EXTERNAL"
        and p.bar_index > leg_start_bar
        and p.bar_index < break_bar
        and p.confirmation_bar_index <= evaluation_bar
        and (break_bar - p.bar_index) <= max_lookback_bars
    ]
    if candidates:
        return min(candidates, key=lambda p: p.pivot_price)

    # STRICT: NO PRE-LEG OR HISTORICAL FALLBACK!
    return None


def find_qualified_rally_high(
    knowable_high_pivots: List[StructuralPivot],
    leg_start_bar: int,
    break_bar: int,
    evaluation_bar: int,
    max_lookback_bars: int = 25,
) -> Optional[StructuralPivot]:
    """Find qualified EXTERNAL high pivot formed during the rally leg between leg_start_bar and break_bar."""
    candidates = [
        p for p in knowable_high_pivots
        if p.classification == "EXTERNAL"
        and p.bar_index > leg_start_bar
        and p.bar_index < break_bar
        and p.confirmation_bar_index <= evaluation_bar
        and (break_bar - p.bar_index) <= max_lookback_bars
    ]
    if candidates:
        return max(candidates, key=lambda p: p.pivot_price)

    # STRICT: NO PRE-LEG OR HISTORICAL FALLBACK!
    return None


def _completion_timestamp(value: str, timeframe: str) -> str:
    normalized = timeframe.strip().lower()
    if not normalized.endswith("m") or not normalized[:-1].isdigit():
        return value
    try:
        completed = pd.Timestamp(value.replace(" UTC", "+00:00")) + pd.Timedelta(
            minutes=int(normalized[:-1])
        )
    except (TypeError, ValueError):
        return value
    if value.endswith(" UTC"):
        return completed.strftime("%Y-%m-%d %H:%M UTC")
    return str(completed)


def detect_structural_pivots(
    bars: pd.DataFrame,
    ext_window: int = 21,
    timeframe: str = "5m",
    evaluation_bar_index: Optional[int] = None,
) -> List[StructuralPivot]:
    """Detect centered structural pivots with strict confirmation lookahead enforcement."""
    if len(bars) < 3:
        return []

    h = bars["high"].to_numpy()
    l = bars["low"].to_numpy()
    n = len(h)
    half_ext = max(1, ext_window // 2)

    if isinstance(bars.index, pd.DatetimeIndex):
        timestamps = [ts.strftime("%Y-%m-%d %H:%M UTC") for ts in bars.index]
    elif "timestamp" in bars.columns:
        timestamps = [str(ts) for ts in bars["timestamp"]]
    else:
        timestamps = [f"bar_{idx}" for idx in range(n)]
    completion_timestamps = [_completion_timestamp(value, timeframe) for value in timestamps]

    pivots: List[StructuralPivot] = []
    eval_idx = n - 1 if evaluation_bar_index is None else evaluation_bar_index

    for i in range(half_ext, n - half_ext):
        confirm_idx = i + half_ext

        # Zero-lookahead gate: pivot is NOT knowable until confirm_idx <= eval_idx
        if confirm_idx > eval_idx:
            continue

        window_h = h[i - half_ext : i + half_ext + 1]
        window_l = l[i - half_ext : i + half_ext + 1]

        if h[i] == np.max(window_h) and np.max(window_h) > np.min(window_h):
            pivots.append(
                StructuralPivot(
                    pivot_id=f"PIVOT_HIGH_{i}_{timeframe}",
                    pivot_type="HIGH",
                    pivot_price=round(float(h[i]), 2),
                    pivot_timestamp=timestamps[i],
                    confirmation_timestamp=completion_timestamps[confirm_idx],
                    knowledge_timestamp=completion_timestamps[confirm_idx],
                    classification="EXTERNAL",
                    timeframe=timeframe,
                    confirmed=True,
                    bar_index=i,
                    confirmation_bar_index=confirm_idx,
                )
            )

        if l[i] == np.min(window_l) and np.max(window_l) > np.min(window_l):
            pivots.append(
                StructuralPivot(
                    pivot_id=f"PIVOT_LOW_{i}_{timeframe}",
                    pivot_type="LOW",
                    pivot_price=round(float(l[i]), 2),
                    pivot_timestamp=timestamps[i],
                    confirmation_timestamp=completion_timestamps[confirm_idx],
                    knowledge_timestamp=completion_timestamps[confirm_idx],
                    classification="EXTERNAL",
                    timeframe=timeframe,
                    confirmed=True,
                    bar_index=i,
                    confirmation_bar_index=confirm_idx,
                )
            )

    return pivots


def compute_atr_series(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Calculate rolling Average True Range (ATR)."""
    n = len(closes)
    if n == 0:
        return np.array([])
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    atr = np.zeros(n)
    if n < period:
        atr[:] = np.mean(tr) if len(tr) > 0 else 1.0
        return atr

    atr[period - 1] = np.mean(tr[:period])
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    for i in range(period - 1):
        atr[i] = atr[period - 1]
    return atr


def extract_and_validate_order_block(
    evt: StructureEvent,
    leg_start_bar: int,
    bars: pd.DataFrame,
    atr_series: np.ndarray,
    timestamps: List[str],
    completion_timestamps: Optional[List[str]] = None,
    symbol: str = "XLK",
    timeframe: str = "5m",
) -> Optional[OrderBlock]:
    """Extract candidate candle and evaluate displacement & structural consequence for Phase 4 Order Block engine."""
    cfg = load_rules_config()
    ob_cfg = cfg.order_block_validation
    min_disp_atr = ob_cfg.min_displacement_atr
    min_body_mult = ob_cfg.min_body_multiplier
    zone_mode = ob_cfg.zone_construction_mode

    h = bars["high"].to_numpy()
    l = bars["low"].to_numpy()
    c = bars["close"].to_numpy()
    o = bars["open"].to_numpy()
    n = len(c)
    knowledge_timestamps = completion_timestamps or timestamps

    try:
        event_bar = int(evt.event_id.split("_")[2])
    except Exception:
        event_bar = n - 1
    event_bar = min(max(0, event_bar), n - 1)

    leg_start = max(0, min(leg_start_bar, event_bar))
    search_start = leg_start
    search_end = max(search_start, event_bar - 1)

    is_bullish = "BULLISH" in evt.event_type

    candidate_idx = None
    if is_bullish:
        for k in range(search_end, search_start - 1, -1):
            if c[k] <= o[k]:
                candidate_idx = k
                break
        if candidate_idx is None and search_end >= search_start:
            candidate_idx = int(search_start + np.argmin(l[search_start : search_end + 1]))
    else:
        for k in range(search_end, search_start - 1, -1):
            if c[k] >= o[k]:
                candidate_idx = k
                break
        if candidate_idx is None and search_end >= search_start:
            candidate_idx = int(search_start + np.argmax(h[search_start : search_end + 1]))

    if candidate_idx is None:
        return None

    k = candidate_idx
    cand_ts = timestamps[k]

    if is_bullish:
        proximal = float(max(o[k], c[k])) if zone_mode == "BODY_TO_EXTREME" else float(h[k])
        distal = float(l[k])
    else:
        proximal = float(min(o[k], c[k])) if zone_mode == "BODY_TO_EXTREME" else float(l[k])
        distal = float(h[k])

    zone_high = round(max(proximal, distal), 2)
    zone_low = round(min(proximal, distal), 2)
    proximal = round(proximal, 2)
    distal = round(distal, 2)

    atr_val = atr_series[event_bar] if event_bar < len(atr_series) else (h[event_bar] - l[event_bar])
    atr_val = max(1e-4, float(atr_val))

    if is_bullish:
        impulse_move = float(np.max(h[k : event_bar + 1])) - float(l[k])
    else:
        impulse_move = float(h[k]) - float(np.min(l[k : event_bar + 1]))

    displacement_atr = impulse_move / atr_val

    win_start = max(0, event_bar - 20)
    bodies = np.abs(c[win_start : event_bar + 1] - o[win_start : event_bar + 1])
    median_body = max(1e-4, float(np.median(bodies)))
    impulse_bodies = np.abs(c[k : event_bar + 1] - o[k : event_bar + 1])
    max_impulse_body = float(np.max(impulse_bodies)) if len(impulse_bodies) > 0 else 0.0
    body_multiplier = max_impulse_body / median_body

    fvg_created = False
    fvg_id = None
    if event_bar - k >= 2:
        for m in range(k + 1, event_bar):
            if is_bullish and l[m + 1] > h[m - 1]:
                fvg_created = True
                fvg_id = f"FVG_{m}_{timeframe}"
                break
            elif not is_bullish and h[m + 1] < l[m - 1]:
                fvg_created = True
                fvg_id = f"FVG_{m}_{timeframe}"
                break

    cand_avail = timestamps[min(k + 1, n - 1)]

    is_displaced = (displacement_atr >= min_disp_atr) or (body_multiplier >= min_body_mult)
    direction = "BULLISH_ORDER_BLOCK" if is_bullish else "BEARISH_ORDER_BLOCK"
    state = "VALIDATED" if is_displaced else "CANDIDATE"

    ob_id = f"OB_{'BULL' if is_bullish else 'BEAR'}_{k}_{timeframe}"

    return OrderBlock(
        order_block_id=ob_id,
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
        state=state,
        candidate_bar_index=k,
        candidate_timestamp=cand_ts,
        candidate_available_at=cand_avail,
        candidate_knowledge_timestamp=cand_avail,
        zone_low=zone_low,
        zone_high=zone_high,
        proximal_price=proximal,
        distal_price=distal,
        validation_event_id=evt.event_id,
        validation_event_type=evt.event_type,
        validation_bar_index=event_bar if is_displaced else None,
        validated_at=knowledge_timestamps[event_bar] if is_displaced else None,
        knowledge_timestamp=knowledge_timestamps[event_bar] if is_displaced else cand_avail,
        source_leg_start_pivot_id=evt.source_pivot_id,
        source_leg_end_event_id=evt.event_id,
        displacement_atr=round(displacement_atr, 2),
        body_multiplier=round(body_multiplier, 2),
        fvg_created=fvg_created,
        fvg_id=fvg_id,
        mitigation_count=0,
        first_mitigation_timestamp=None,
        last_mitigation_timestamp=None,
        mitigation_depth_pct=0.0,
        invalidation_timestamp=None,
        expiration_timestamp=None,
        candidate_age_bars=0,
        validation_age_bars=0,
        age_bars=0,
        config_version=cfg.version,
        engine_version="v4.1.0",
        evidence_ladder={
            "event_type": evt.event_type,
            "displacement_atr": round(displacement_atr, 2),
            "body_multiplier": round(body_multiplier, 2),
            "fvg_created": fvg_created,
        },
    )


def update_order_block_lifecycles(
    order_blocks: List[OrderBlock],
    bars: pd.DataFrame,
    atr_series: np.ndarray,
    timestamps: List[str],
    current_bar_idx: int,
    timeframe: str = "5m",
):
    """Update age, mitigation depth, invalidation, and expiration status of Order Blocks as of current_bar_idx."""
    cfg = load_rules_config()
    ob_cfg = cfg.order_block_validation
    max_age_dict = ob_cfg.max_age_bars
    max_age = max_age_dict.get(timeframe, 50)

    atr_buffer = ob_cfg.invalidation.get("atr_buffer", 0.0)

    c = bars["close"].to_numpy()
    h = bars["high"].to_numpy()
    l = bars["low"].to_numpy()
    curr_ts = timestamps[current_bar_idx]
    curr_atr = atr_series[current_bar_idx] if current_bar_idx < len(atr_series) else 0.0

    for ob in order_blocks:
        ob.candidate_age_bars = current_bar_idx - ob.candidate_bar_index
        if ob.validation_bar_index is not None:
            ob.validation_age_bars = max(0, current_bar_idx - ob.validation_bar_index)
            ob.age_bars = ob.validation_age_bars
        else:
            ob.validation_age_bars = 0
            ob.age_bars = ob.candidate_age_bars

        # Terminal states are immutable
        if ob.state in ("INVALIDATED", "EXPIRED"):
            continue

        # Expiration Check based on validation_age_bars (or candidate_age_bars if CANDIDATE)
        eval_age = ob.validation_age_bars if ob.validation_bar_index is not None else ob.candidate_age_bars
        if eval_age > max_age:
            ob.state = "EXPIRED"
            if not ob.expiration_timestamp:
                ob.expiration_timestamp = curr_ts
            continue

        # Validation-Time Lifecycle Causality Gate:
        # Price action evaluation MUST begin strictly AFTER validation event (or after candidate close for CANDIDATE)
        eval_start_bar = ob.validation_bar_index if ob.validation_bar_index is not None else ob.candidate_bar_index
        if current_bar_idx <= eval_start_bar:
            continue

        bar_close = float(c[current_bar_idx])
        bar_high = float(h[current_bar_idx])
        bar_low = float(l[current_bar_idx])

        # Invalidation Check (CLOSE_BEYOND_DISTAL)
        is_invalidated = False
        if ob.direction == "BULLISH_ORDER_BLOCK":
            inval_level = ob.distal_price - (curr_atr * atr_buffer)
            if bar_close < inval_level:
                is_invalidated = True
        else:
            inval_level = ob.distal_price + (curr_atr * atr_buffer)
            if bar_close > inval_level:
                is_invalidated = True

        if is_invalidated:
            ob.state = "INVALIDATED"
            if not ob.invalidation_timestamp:
                ob.invalidation_timestamp = curr_ts
            continue

        # Mitigation Check (Price enters zone post-validation)
        if ob.state in ("VALIDATED", "MITIGATED"):
            is_mitigated_this_bar = False
            if ob.direction == "BULLISH_ORDER_BLOCK":
                if bar_low <= ob.proximal_price:
                    is_mitigated_this_bar = True
                    depth = (ob.proximal_price - bar_low) / max(1e-4, ob.proximal_price - ob.distal_price) * 100.0
                    ob.mitigation_depth_pct = min(100.0, max(ob.mitigation_depth_pct, float(depth)))
            else:
                if bar_high >= ob.proximal_price:
                    is_mitigated_this_bar = True
                    depth = (bar_high - ob.proximal_price) / max(1e-4, ob.distal_price - ob.proximal_price) * 100.0
                    ob.mitigation_depth_pct = min(100.0, max(ob.mitigation_depth_pct, float(depth)))

            if is_mitigated_this_bar:
                ob.state = "MITIGATED"
                ob.mitigation_count += 1
                if not ob.first_mitigation_timestamp:
                    ob.first_mitigation_timestamp = curr_ts
                ob.last_mitigation_timestamp = curr_ts


def analyze_smc_structure(
    bars: pd.DataFrame,
    is_fast_chart: bool = False,
    symbol: str = "XLK",
    timeframe: str = "5m",
    break_confirmation_mode: str = "CLOSE",
    evaluation_bar_index: Optional[int] = None,
) -> SMCAnalysisResult:
    """Analyze OHLCV DataFrame for institutional SMC structure with 0-lookahead pivots & explicit state machine."""
    if len(bars) < 5:
        return SMCAnalysisResult(
            regime="NEUTRAL",
            latest_bos=None,
            latest_choch=None,
            latest_event=None,
            events=[],
            confirmed_pivots=[],
            demand_ob=None,
            supply_ob=None,
            liquidity_pools=[],
            structure_score=50.0,
        )

    h = bars["high"].to_numpy()
    l = bars["low"].to_numpy()
    c = bars["close"].to_numpy()
    o = bars["open"].to_numpy()
    n = len(c)
    eval_idx = n - 1 if evaluation_bar_index is None else evaluation_bar_index
    eval_idx = min(max(0, eval_idx), n - 1)

    if isinstance(bars.index, pd.DatetimeIndex):
        timestamps = [ts.strftime("%Y-%m-%d %H:%M UTC") for ts in bars.index]
    elif "timestamp" in bars.columns:
        timestamps = [str(ts) for ts in bars["timestamp"]]
    else:
        timestamps = [f"bar_{idx}" for idx in range(n)]
    completion_timestamps = [_completion_timestamp(value, timeframe) for value in timestamps]

    ext_window = 5 if (is_fast_chart or n < 50) else 21
    pivots = detect_structural_pivots(bars, ext_window=ext_window, timeframe=timeframe, evaluation_bar_index=eval_idx)

    # Configured max lookback bars for timeframe
    max_lookback_bars = get_max_leg_lookback_bars(timeframe)

    # Sort pivots by confirmation_bar_index then bar_index
    pivots = sorted(pivots, key=lambda p: (p.confirmation_bar_index, p.bar_index))

    # Precompute rolling ATR series for Order Block displacement & invalidation
    atr_series = compute_atr_series(h, l, c, period=14)

    # Structural State Machine
    current_state = "NEUTRAL"
    protected_low: Optional[ProtectedSwing] = None
    protected_high: Optional[ProtectedSwing] = None
    active_high: Optional[ProtectedSwing] = None
    active_low: Optional[ProtectedSwing] = None

    events: List[StructureEvent] = []
    broken_pivot_ids: Set[str] = set()

    all_order_blocks: List[OrderBlock] = []

    pivot_cursor = 0
    num_pivots = len(pivots)

    knowable_high_pivots: List[StructuralPivot] = []
    knowable_low_pivots: List[StructuralPivot] = []

    for i in range(eval_idx + 1):
        # 1. Update available pivots as of bar i (knowledge_timestamp <= timestamps[i])
        while pivot_cursor < num_pivots and pivots[pivot_cursor].confirmation_bar_index <= i:
            piv = pivots[pivot_cursor]
            pivot_cursor += 1
            if piv.pivot_type == "HIGH":
                knowable_high_pivots.append(piv)
                active_high = ProtectedSwing(
                    role="ACTIVE_HIGH",
                    swing_type="ACTIVE_HIGH",
                    price=piv.pivot_price,
                    pivot_id=piv.pivot_id,
                    pivot_timestamp=piv.pivot_timestamp,
                    knowledge_timestamp=piv.knowledge_timestamp,
                    promoted_at=completion_timestamps[i],
                    promoted_by_event_id=None,
                    timeframe=timeframe,
                    bar_index=piv.bar_index,
                    confirmation_bar_index=piv.confirmation_bar_index,
                )
            elif piv.pivot_type == "LOW":
                knowable_low_pivots.append(piv)
                active_low = ProtectedSwing(
                    role="ACTIVE_LOW",
                    swing_type="ACTIVE_LOW",
                    price=piv.pivot_price,
                    pivot_id=piv.pivot_id,
                    pivot_timestamp=piv.pivot_timestamp,
                    knowledge_timestamp=piv.knowledge_timestamp,
                    promoted_at=completion_timestamps[i],
                    promoted_by_event_id=None,
                    timeframe=timeframe,
                    bar_index=piv.bar_index,
                    confirmation_bar_index=piv.confirmation_bar_index,
                )

        # 2. Evaluate structural break against bar i
        bar_close = float(c[i])
        bar_high = float(h[i])
        bar_low = float(l[i])

        if break_confirmation_mode == "WICK":
            eval_high = bar_high
            eval_low = bar_low
        else:
            eval_high = bar_close
            eval_low = bar_close

        prev_state = current_state
        event_emitted_this_bar = False
        new_event: Optional[StructureEvent] = None
        leg_start_for_ob = 0

        # Priority Evaluation (CHoCH -> BOS -> INITIAL_BREAK)
        if prev_state == "BULLISH":
            # Priority 1: Invalidation / BEARISH_CHOCH
            if protected_low and eval_low < protected_low.price and protected_low.pivot_id not in broken_pivot_ids:
                broken_pivot_ids.add(protected_low.pivot_id)
                evt_id = f"EVT_CHOCH_{i}_{timeframe}"
                new_event = StructureEvent(
                    event_id=evt_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    event_type="BEARISH_CHOCH",
                    direction="BEARISH",
                    level_broken=protected_low.price,
                    event_timestamp=timestamps[i],
                    knowledge_timestamp=completion_timestamps[i],
                    previous_structure_state=prev_state,
                    new_structure_state="BEARISH",
                    source_pivot_id=protected_low.pivot_id,
                    confirmation_method=break_confirmation_mode,
                )
                events.append(new_event)
                current_state = "BEARISH"
                event_emitted_this_bar = True
                leg_start_for_ob = protected_low.bar_index

                # Retire Bullish protected_low cleanly
                retired_low_id = protected_low.pivot_id
                protected_low = None

                # Establish Bearish protected_high from highest knowable confirmed high pivot
                target_high = find_qualified_rally_high(
                    knowable_high_pivots,
                    leg_start_bar=max(0, i - max_lookback_bars),
                    break_bar=i,
                    evaluation_bar=i,
                    max_lookback_bars=max_lookback_bars,
                )
                if target_high:
                    protected_high = ProtectedSwing(
                        role="PROTECTED_HIGH",
                        swing_type="PROTECTED_HIGH",
                        price=target_high.pivot_price,
                        pivot_id=target_high.pivot_id,
                        pivot_timestamp=target_high.pivot_timestamp,
                        knowledge_timestamp=target_high.knowledge_timestamp,
                        promoted_at=completion_timestamps[i],
                        promoted_by_event_id=evt_id,
                        selection_reason="CHOCH_TRANSITION",
                        source_leg_start_pivot_id=retired_low_id,
                        source_leg_end_event_id=evt_id,
                        timeframe=timeframe,
                        bar_index=target_high.bar_index,
                        confirmation_bar_index=target_high.confirmation_bar_index,
                    )
                else:
                    protected_high = None

            # Priority 2: Continuation / BULLISH_BOS
            elif not event_emitted_this_bar and active_high and eval_high > active_high.price and active_high.pivot_id not in broken_pivot_ids:
                broken_pivot_ids.add(active_high.pivot_id)
                evt_id = f"EVT_BOS_{i}_{timeframe}"
                new_event = StructureEvent(
                    event_id=evt_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    event_type="BULLISH_BOS",
                    direction="BULLISH",
                    level_broken=active_high.price,
                    event_timestamp=timestamps[i],
                    knowledge_timestamp=completion_timestamps[i],
                    previous_structure_state=prev_state,
                    new_structure_state="BULLISH",
                    source_pivot_id=active_high.pivot_id,
                    confirmation_method=break_confirmation_mode,
                )
                events.append(new_event)
                current_state = "BULLISH"
                event_emitted_this_bar = True
                leg_start_for_ob = protected_low.bar_index if protected_low else max(0, active_high.bar_index - max_lookback_bars)

                # Promote qualified low pivot belonging strictly to the BOS structural leg
                leg_start = protected_low.bar_index if protected_low else (active_high.bar_index - 1)
                target_low = find_qualified_pullback_low(
                    knowable_low_pivots,
                    leg_start_bar=leg_start,
                    break_bar=i,
                    evaluation_bar=i,
                    max_lookback_bars=max_lookback_bars,
                )
                if target_low:
                    protected_low = ProtectedSwing(
                        role="PROTECTED_LOW",
                        swing_type="PROTECTED_LOW",
                        price=target_low.pivot_price,
                        pivot_id=target_low.pivot_id,
                        pivot_timestamp=target_low.pivot_timestamp,
                        knowledge_timestamp=target_low.knowledge_timestamp,
                        promoted_at=completion_timestamps[i],
                        promoted_by_event_id=evt_id,
                        selection_reason="PULLBACK_BEFORE_BOS",
                        source_leg_start_pivot_id=active_high.pivot_id,
                        source_leg_end_event_id=evt_id,
                        timeframe=timeframe,
                        bar_index=target_low.bar_index,
                        confirmation_bar_index=target_low.confirmation_bar_index,
                    )
                else:
                    protected_low = None

        elif prev_state == "BEARISH":
            # Priority 1: Invalidation / BULLISH_CHOCH
            if protected_high and eval_high > protected_high.price and protected_high.pivot_id not in broken_pivot_ids:
                broken_pivot_ids.add(protected_high.pivot_id)
                evt_id = f"EVT_CHOCH_{i}_{timeframe}"
                new_event = StructureEvent(
                    event_id=evt_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    event_type="BULLISH_CHOCH",
                    direction="BULLISH",
                    level_broken=protected_high.price,
                    event_timestamp=timestamps[i],
                    knowledge_timestamp=completion_timestamps[i],
                    previous_structure_state=prev_state,
                    new_structure_state="BULLISH",
                    source_pivot_id=protected_high.pivot_id,
                    confirmation_method=break_confirmation_mode,
                )
                events.append(new_event)
                current_state = "BULLISH"
                event_emitted_this_bar = True
                leg_start_for_ob = protected_high.bar_index

                # Retire Bearish protected_high cleanly
                retired_high_id = protected_high.pivot_id
                protected_high = None

                # Establish Bullish protected_low from lowest knowable confirmed low pivot
                target_low = find_qualified_pullback_low(
                    knowable_low_pivots,
                    leg_start_bar=max(0, i - max_lookback_bars),
                    break_bar=i,
                    evaluation_bar=i,
                    max_lookback_bars=max_lookback_bars,
                )
                if target_low:
                    protected_low = ProtectedSwing(
                        role="PROTECTED_LOW",
                        swing_type="PROTECTED_LOW",
                        price=target_low.pivot_price,
                        pivot_id=target_low.pivot_id,
                        pivot_timestamp=target_low.pivot_timestamp,
                        knowledge_timestamp=target_low.knowledge_timestamp,
                        promoted_at=completion_timestamps[i],
                        promoted_by_event_id=evt_id,
                        selection_reason="CHOCH_TRANSITION",
                        source_leg_start_pivot_id=retired_high_id,
                        source_leg_end_event_id=evt_id,
                        timeframe=timeframe,
                        bar_index=target_low.bar_index,
                        confirmation_bar_index=target_low.confirmation_bar_index,
                    )
                else:
                    protected_low = None

            # Priority 2: Continuation / BEARISH_BOS
            elif not event_emitted_this_bar and active_low and eval_low < active_low.price and active_low.pivot_id not in broken_pivot_ids:
                broken_pivot_ids.add(active_low.pivot_id)
                evt_id = f"EVT_BOS_{i}_{timeframe}"
                new_event = StructureEvent(
                    event_id=evt_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    event_type="BEARISH_BOS",
                    direction="BEARISH",
                    level_broken=active_low.price,
                    event_timestamp=timestamps[i],
                    knowledge_timestamp=completion_timestamps[i],
                    previous_structure_state=prev_state,
                    new_structure_state="BEARISH",
                    source_pivot_id=active_low.pivot_id,
                    confirmation_method=break_confirmation_mode,
                )
                events.append(new_event)
                current_state = "BEARISH"
                event_emitted_this_bar = True
                leg_start_for_ob = protected_high.bar_index if protected_high else max(0, active_low.bar_index - max_lookback_bars)

                # Promote qualified high pivot belonging strictly to the BOS structural leg
                leg_start = protected_high.bar_index if protected_high else (active_low.bar_index - 1)
                target_high = find_qualified_rally_high(
                    knowable_high_pivots,
                    leg_start_bar=leg_start,
                    break_bar=i,
                    evaluation_bar=i,
                    max_lookback_bars=max_lookback_bars,
                )
                if target_high:
                    protected_high = ProtectedSwing(
                        role="PROTECTED_HIGH",
                        swing_type="PROTECTED_HIGH",
                        price=target_high.pivot_price,
                        pivot_id=target_high.pivot_id,
                        pivot_timestamp=target_high.pivot_timestamp,
                        knowledge_timestamp=target_high.knowledge_timestamp,
                        promoted_at=completion_timestamps[i],
                        promoted_by_event_id=evt_id,
                        selection_reason="RALLY_BEFORE_BOS",
                        source_leg_start_pivot_id=active_low.pivot_id,
                        source_leg_end_event_id=evt_id,
                        timeframe=timeframe,
                        bar_index=target_high.bar_index,
                        confirmation_bar_index=target_high.confirmation_bar_index,
                    )
                else:
                    protected_high = None

        elif prev_state == "NEUTRAL":
            # Priority 3: Initial Breaks
            if active_high and eval_high > active_high.price and active_high.pivot_id not in broken_pivot_ids:
                broken_pivot_ids.add(active_high.pivot_id)
                evt_id = f"EVT_INIT_{i}_{timeframe}"
                new_event = StructureEvent(
                    event_id=evt_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    event_type="BULLISH_INITIAL_BREAK",
                    direction="BULLISH",
                    level_broken=active_high.price,
                    event_timestamp=timestamps[i],
                    knowledge_timestamp=completion_timestamps[i],
                    previous_structure_state=prev_state,
                    new_structure_state="BULLISH",
                    source_pivot_id=active_high.pivot_id,
                    confirmation_method=break_confirmation_mode,
                )
                events.append(new_event)
                current_state = "BULLISH"
                event_emitted_this_bar = True
                leg_start_for_ob = max(0, active_high.bar_index - max_lookback_bars)

                # Bootstrap protected_low from local structural leg leading to active_high
                leg_start = max(0, active_high.bar_index - max_lookback_bars)
                target_low = find_qualified_pullback_low(
                    knowable_low_pivots,
                    leg_start_bar=leg_start,
                    break_bar=i,
                    evaluation_bar=i,
                    max_lookback_bars=max_lookback_bars,
                )
                if target_low:
                    protected_low = ProtectedSwing(
                        role="PROTECTED_LOW",
                        swing_type="PROTECTED_LOW",
                        price=target_low.pivot_price,
                        pivot_id=target_low.pivot_id,
                        pivot_timestamp=target_low.pivot_timestamp,
                        knowledge_timestamp=target_low.knowledge_timestamp,
                        promoted_at=completion_timestamps[i],
                        promoted_by_event_id=evt_id,
                        selection_reason="INITIAL_BREAK_BASE",
                        source_leg_start_pivot_id=active_high.pivot_id,
                        source_leg_end_event_id=evt_id,
                        timeframe=timeframe,
                        bar_index=target_low.bar_index,
                        confirmation_bar_index=target_low.confirmation_bar_index,
                    )
                else:
                    protected_low = None
                protected_high = None

            elif not event_emitted_this_bar and active_low and eval_low < active_low.price and active_low.pivot_id not in broken_pivot_ids:
                broken_pivot_ids.add(active_low.pivot_id)
                evt_id = f"EVT_INIT_{i}_{timeframe}"
                new_event = StructureEvent(
                    event_id=evt_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    event_type="BEARISH_INITIAL_BREAK",
                    direction="BEARISH",
                    level_broken=active_low.price,
                    event_timestamp=timestamps[i],
                    knowledge_timestamp=completion_timestamps[i],
                    previous_structure_state=prev_state,
                    new_structure_state="BEARISH",
                    source_pivot_id=active_low.pivot_id,
                    confirmation_method=break_confirmation_mode,
                )
                events.append(new_event)
                current_state = "BEARISH"
                event_emitted_this_bar = True
                leg_start_for_ob = max(0, active_low.bar_index - max_lookback_bars)

                # Bootstrap protected_high from local structural leg leading to active_low
                leg_start = max(0, active_low.bar_index - max_lookback_bars)
                target_high = find_qualified_rally_high(
                    knowable_high_pivots,
                    leg_start_bar=leg_start,
                    break_bar=i,
                    evaluation_bar=i,
                    max_lookback_bars=max_lookback_bars,
                )
                if target_high:
                    protected_high = ProtectedSwing(
                        role="PROTECTED_HIGH",
                        swing_type="PROTECTED_HIGH",
                        price=target_high.pivot_price,
                        pivot_id=target_high.pivot_id,
                        pivot_timestamp=target_high.pivot_timestamp,
                        knowledge_timestamp=target_high.knowledge_timestamp,
                        promoted_at=completion_timestamps[i],
                        promoted_by_event_id=evt_id,
                        selection_reason="INITIAL_BREAK_BASE",
                        source_leg_start_pivot_id=active_low.pivot_id,
                        source_leg_end_event_id=evt_id,
                        timeframe=timeframe,
                        bar_index=target_high.bar_index,
                        confirmation_bar_index=target_high.confirmation_bar_index,
                    )
                else:
                    protected_high = None
                protected_low = None

        # 3. Phase 4 Order Block Pipeline Trigger & Lifecycle Update
        if new_event is not None:
            ob = extract_and_validate_order_block(
                evt=new_event,
                leg_start_bar=leg_start_for_ob,
                bars=bars,
                atr_series=atr_series,
                timestamps=timestamps,
                completion_timestamps=completion_timestamps,
                symbol=symbol,
                timeframe=timeframe,
            )
            if ob is not None:
                all_order_blocks.append(ob)

        # Update order block lifecycles as of bar i
        update_order_block_lifecycles(
            order_blocks=all_order_blocks,
            bars=bars,
            atr_series=atr_series,
            timestamps=timestamps,
            current_bar_idx=i,
            timeframe=timeframe,
        )

    latest_evt = events[-1] if events else None
    latest_bos = None
    latest_choch = None

    for evt in reversed(events):
        if "BOS" in evt.event_type and latest_bos is None:
            latest_bos = evt.event_type
        if "CHOCH" in evt.event_type and latest_choch is None:
            latest_choch = evt.event_type
        if latest_bos and latest_choch:
            break

    # Select latest active demand_ob and supply_ob
    valid_bullish = [ob for ob in all_order_blocks if ob.direction == "BULLISH_ORDER_BLOCK" and ob.state in ("VALIDATED", "MITIGATED")]
    demand_ob = valid_bullish[-1] if valid_bullish else None

    valid_bearish = [ob for ob in all_order_blocks if ob.direction == "BEARISH_ORDER_BLOCK" and ob.state in ("VALIDATED", "MITIGATED")]
    supply_ob = valid_bearish[-1] if valid_bearish else None

    # Liquidity Pool Detection (EQH / EQL)
    liquidity_pools = []
    high_pivots = [p for p in pivots if p.pivot_type == "HIGH"]
    low_pivots = [p for p in pivots if p.pivot_type == "LOW"]

    if len(high_pivots) >= 2:
        latest_high, prior_high = high_pivots[-1], high_pivots[-2]
        h1, h2 = latest_high.pivot_price, prior_high.pivot_price
        if abs(h1 - h2) / h2 <= 0.0015:
            liquidity_pools.append(
                LiquidityPool(
                    pool_id=f"EQH_{prior_high.pivot_id}_{latest_high.pivot_id}",
                    pool_type="EQH",
                    price=round((h1 + h2) / 2, 2),
                    source_pivot_ids=[prior_high.pivot_id, latest_high.pivot_id],
                    knowledge_timestamp=latest_high.knowledge_timestamp,
                )
            )
    if len(low_pivots) >= 2:
        latest_low, prior_low = low_pivots[-1], low_pivots[-2]
        l1, l2 = latest_low.pivot_price, prior_low.pivot_price
        if abs(l1 - l2) / l2 <= 0.0015:
            liquidity_pools.append(
                LiquidityPool(
                    pool_id=f"EQL_{prior_low.pivot_id}_{latest_low.pivot_id}",
                    pool_type="EQL",
                    price=round((l1 + l2) / 2, 2),
                    source_pivot_ids=[prior_low.pivot_id, latest_low.pivot_id],
                    knowledge_timestamp=latest_low.knowledge_timestamp,
                )
            )

    # Structure Score Calculation
    score = 50.0
    if current_state == "BULLISH":
        score = 80.0
        if latest_bos == "BULLISH_BOS":
            score = 92.0
        elif latest_choch == "BULLISH_CHOCH":
            score = 88.0
    elif current_state == "BEARISH":
        score = 20.0
        if latest_bos == "BEARISH_BOS":
            score = 8.0
        elif latest_choch == "BEARISH_CHOCH":
            score = 12.0

    curr_price = float(c[eval_idx])
    if demand_ob and not demand_ob.is_mitigated and demand_ob.bottom_price <= curr_price <= demand_ob.top_price * 1.005:
        score = min(98.0, score + 10.0)

    return SMCAnalysisResult(
        regime=current_state,
        latest_bos=latest_bos,
        latest_choch=latest_choch,
        latest_event=latest_evt,
        events=events,
        confirmed_pivots=pivots,
        protected_low=protected_low,
        protected_high=protected_high,
        active_high=active_high,
        active_low=active_low,
        demand_ob=demand_ob,
        supply_ob=supply_ob,
        order_blocks=all_order_blocks,
        liquidity_pools=liquidity_pools,
        structure_score=round(score, 2),
    )
