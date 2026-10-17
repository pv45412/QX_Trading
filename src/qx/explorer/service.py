"""Sector / Industry Explorer service.

Answers, for one sector or industry ETF:

  * which of its stocks have momentum UP **and** trend UP (TOPS-MultiTrend),
  * which lead their parent ETF and the market (synchronised horizons),
  * how broad the participation is (breadth with an explicit denominator), and
  * whether an aligned stock's ENTRY is attractive, separate from alignment.

Entry quality uses QX MASTER AUTO FAST's own plan levels (ATR stop, 1R/2R
targets) and its regime/ready/active ladder. Alignment NEVER produces
``EXECUTABLE`` here: that state stays gated behind the repository's
``publication_state == VERIFIED and executable is True`` rule, which this layer
cannot set. The strongest thing alignment alone can reach is ``TRIGGER_CONFIRMED``.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from qx.explorer import market_phases, master_auto, membership, momo_trend
from qx.scanner.engine import MarketData
from qx.scanner.studies import SECTOR_ETFS

MARKET_BENCHMARK = "SPY"

# Industry ETFs worth exploring beyond the 11 sectors (extendable).
INDUSTRY_ETFS: tuple[tuple[str, str, str], ...] = (
    ("SMH", "Semiconductors", "Technology"),
    ("IGV", "Software", "Technology"),
    ("CIBR", "Cybersecurity", "Technology"),
    ("XBI", "Biotech", "Health Care"),
    ("KRE", "Regional Banks", "Financials"),
    ("XOP", "Oil & Gas E&P", "Energy"),
    ("GDX", "Gold Miners", "Materials"),
    ("JETS", "Airlines", "Industrials"),
    ("ITB", "Homebuilders", "Consumer Discretionary"),
    ("XRT", "Retail", "Consumer Discretionary"),
    ("XME", "Metals & Mining", "Materials"),
    ("XHB", "Home Construction", "Consumer Discretionary"),
)

UNIVERSE_CHOICES = (
    {"id": membership.UNIVERSE_HOLDINGS, "label": "ETF Holdings",
     "description": "Sourced holdings with weights (top 25 served by the source)"},
    {"id": membership.UNIVERSE_MEMBERS, "label": "Sector/Industry Members",
     "description": "Sourced classified constituents (no weights)"},
)

# ------------------------------------------------------------------ entry quality
ENTRY_PULLBACK = "PULLBACK_CANDIDATE"
ENTRY_BREAKOUT = "BREAKOUT_WATCH"
ENTRY_TRIGGER = "TRIGGER_CONFIRMED"
ENTRY_EXTENDED = "EXTENDED_WAIT"
ENTRY_BLOCKED_RESISTANCE = "BLOCKED_RESISTANCE"
ENTRY_BLOCKED_DATA = "BLOCKED_DATA"
ENTRY_BLOCKED_AMBIGUOUS = "BLOCKED_AMBIGUOUS"
ENTRY_NONE = "NOT_ALIGNED"

# Study state is kept SEPARATE from current entry eligibility (reviewer F01/F13).
STUDY_SIGNAL = "ACTIVE_STUDY_SIGNAL"
ELIGIBILITY_READY = "ENTRY_ELIGIBLE"
ELIGIBILITY_EXPIRED = "ENTRY_EXPIRED"
ELIGIBILITY_INVALIDATED = "ENTRY_INVALIDATED"

# Extension cutoffs — declared, configurable, and NOT claimed as optimal.
DEFAULT_CONFIG = {
    "extended_atr_multiple": 1.5,       # beyond this from the trigger = too extended to chase
    "near_trigger_atr": 0.5,
    "min_history_bars": 180,
    "benchmark": MARKET_BENCHMARK,
    # Phase A: a latched signal only counts as CURRENT readiness if it is fresh
    # and price is still inside a tradable window. Without these, a stale latch is
    # promoted to "Ready now" (reviewer F01).
    "signal_max_age_bars": 3,
    "entry_window_atr": 1.5,
    "atr_stop_multiplier": 1.10,
    "target_r": 2.00,
}


# --------------------------------------------------------------------------- #
# Side-aware plan construction (reviewer F02/F03)
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# PLANNED R:R IS A CONFIGURED CONSTANT, NOT A MEASUREMENT.
#
# long_plan/short_plan compute the target as trigger +/- atr * mult * target_r, so
# the ratio they report is exactly target_r (2.00) for every symbol, every side,
# every timeframe. It is arithmetic identity, not evidence. Measured against a
# 2-year backtest over 400 symbols, the REALISED long-side result was +0.41 R per
# trade (PF 1.37), median -0.59 R, and only 40.6% of trades reached their target
# side at all. Presenting a configured 2.00 beside a live plan reads as an
# expected payoff; it is not one.
#
# The number is retained (the target price is a legitimate planning level) but
# labelled as configured rather than realised, so no surface implies an edge.
# --------------------------------------------------------------------------- #

REWARD_RISK_BASIS = "CONFIGURED_TARGET"
REWARD_RISK_NOTE = (
    "Planned R:R is the configured target multiple, not a measured outcome. The "
    "target sits at a fixed ATR multiple, so this ratio is identical for every "
    "setup. Realised performance over a 2-year backtest was +0.41 R per trade on "
    "the long side (profit factor 1.37), with 40.6% of trades profitable."
)
REALISED_LONG_MEAN_R = 0.41
REALISED_LONG_WIN_RATE = 0.406
REALISED_LONG_PROFIT_FACTOR = 1.37


def long_plan(trigger: float, atr: float, cfg: dict[str, Any]) -> dict[str, Any]:
    """A LONG plan: target above, invalidation below, chase limit ABOVE trigger."""
    mult = cfg["atr_stop_multiplier"]
    return {
        "direction": "LONG",
        "trigger": round(trigger, 4),
        "invalidation": round(trigger - atr * mult, 4),
        "target": round(trigger + atr * mult * cfg["target_r"], 4),
        "reward_risk": cfg["target_r"],
        "reward_risk_basis": REWARD_RISK_BASIS,
        "reward_risk_note": REWARD_RISK_NOTE,
        "realised_mean_r": REALISED_LONG_MEAN_R,
        "chase_limit": round(trigger + atr * cfg["extended_atr_multiple"], 4),
    }


def short_plan(trigger: float, atr: float, cfg: dict[str, Any]) -> dict[str, Any]:
    """A SHORT plan: target below, invalidation above, chase limit BELOW trigger."""
    mult = cfg["atr_stop_multiplier"]
    return {
        "direction": "SHORT",
        "trigger": round(trigger, 4),
        "invalidation": round(trigger + atr * mult, 4),
        "target": round(trigger - atr * mult * cfg["target_r"], 4),
        "reward_risk": cfg["target_r"],
        "reward_risk_basis": REWARD_RISK_BASIS,
        "reward_risk_note": REWARD_RISK_NOTE,
        # Shorts measured at -0.60 R; see SHORT_SIDE_NOTE.
        "realised_mean_r": -0.60,
        "chase_limit": round(trigger - atr * cfg["extended_atr_multiple"], 4),
    }


def catalog() -> dict[str, Any]:
    """Every explorable sector and industry ETF with its parent sector."""
    sectors = [{"symbol": s, "name": n, "kind": "SECTOR", "parent": None} for s, n in SECTOR_ETFS]
    industries = [{"symbol": s, "name": n, "kind": "INDUSTRY", "parent": p} for s, n, p in INDUSTRY_ETFS]
    return {
        "sectors": sectors,
        "industries": industries,
        "universes": list(UNIVERSE_CHOICES),
        "count": len(sectors) + len(industries),
    }


def _config(overrides: dict[str, Any] | None) -> dict[str, Any]:
    return {**DEFAULT_CONFIG, **(overrides or {})}


# --------------------------------------------------------------------------- #
# Reconciliation: a stock's returns vs parent and market on matched horizons
# --------------------------------------------------------------------------- #

def _dated_index(bars: list[dict]) -> dict[str, float]:
    """Close price keyed by CALENDAR DATE (F10). Undated bars are skipped."""
    out: dict[str, float] = {}
    for bar in bars:
        stamp = bar.get("date")
        if not stamp:
            continue
        day = str(stamp)[:10]
        close = bar.get("close")
        if close:
            out[day] = float(close)
    return out


def _returns(bars: list[dict], horizons: tuple[int, ...] = (5, 20, 60)) -> dict[int, float | None]:
    """Simple returns over N BARS (positional). Retained for undated series."""
    out: dict[int, float | None] = {}
    for h in horizons:
        if len(bars) <= h or bars[-1 - h]["close"] == 0:
            out[h] = None
        else:
            out[h] = bars[-1]["close"] / bars[-1 - h]["close"] - 1.0
    return out


def _relative(stock_bars: list[dict], ref_bars: list[dict], horizon: int) -> float | None:
    """Excess return over a horizon.

    Reviewer F10: when both series carry dates, the comparison is made over the
    SAME CALENDAR WINDOW (a symbol that did not trade on the earliest date is not
    silently compared from a different start). Positional comparison is used only
    when dates are unavailable, and that case is reported as ``basis``.
    """
    own_dated, ref_dated = _dated_index(stock_bars), _dated_index(ref_bars)
    if own_dated and ref_dated:
        common = sorted(set(own_dated) & set(ref_dated))
        if len(common) > horizon:
            start, end = common[-1 - horizon], common[-1]
            base_own, base_ref = own_dated[start], ref_dated[start]
            if base_own and base_ref:
                own_ret = own_dated[end] / base_own - 1.0
                ref_ret = ref_dated[end] / base_ref - 1.0
                return round((own_ret - ref_ret) * 100.0, 2)
        return None
    own = _returns(stock_bars, (horizon,))[horizon]
    ref = _returns(ref_bars, (horizon,))[horizon]
    if own is None or ref is None:
        return None
    return round((own - ref) * 100.0, 2)


def _relative_basis(stock_bars: list[dict], ref_bars: list[dict]) -> str:
    """Which basis a relative-strength figure used — 'DATE_ALIGNED' or 'POSITIONAL'."""
    if _dated_index(stock_bars) and _dated_index(ref_bars):
        return "DATE_ALIGNED"
    return "POSITIONAL"


# --------------------------------------------------------------------------- #
# Entry quality — deliberately separate from alignment
# --------------------------------------------------------------------------- #

def _proposed_direction(snapshot: Any) -> tuple[str | None, str]:
    """Direction from the QUALIFYING CONDITION — never from the latched direction.

    Reviewer F02/F13: a bearish watch must not inherit a call-side trigger, and the
    candidate's own alignment must not silently override the plan's direction.
    """
    bull = bool(getattr(snapshot, "call_ready", False) or getattr(snapshot, "bull_build", False))
    bear = bool(getattr(snapshot, "put_ready", False) or getattr(snapshot, "bear_build", False))
    if bull and bear:
        return None, "AMBIGUOUS"
    if bull:
        return "LONG", "CALL_CONDITION"
    if bear:
        return "SHORT", "PUT_CONDITION"
    return None, "NONE"


def _normalise_interval(timeframe: str) -> str | None:
    """Map a requested timeframe to a supported bar interval, else None (F08)."""
    value = str(timeframe or "").strip().lower()
    if value in {"1d", "daily", "day", "swing", "d"}:
        return "1d"
    if value in {"1m", "5m", "15m", "30m"}:
        return value
    if value.isdigit():
        candidate = f"{value}m"
        return candidate if candidate in {"1m", "5m", "15m", "30m"} else None
    return None


def _row_observation_time(row: dict[str, Any]) -> str | None:
    """When the row's data was observed, preferring the quote's own timestamp (F06)."""
    return row.get("observed_at") or row.get("as_of")


def _freshness(quote: dict | None, bars: list[dict], quote_source: str,
               bar_source: str) -> dict[str, Any]:
    """Classify data freshness from REAL observation times (F06/F10/F14).

    Returns UNKNOWN when no observation timestamp exists — which is the honest
    answer for cache-backed rows, and is what makes a freshness gate meaningful.
    """
    from qx.signals.freshness import FreshnessChecker

    stamp = (quote or {}).get("timestamp")
    bar_stamp = bars[-1].get("date") if bars else None

    quote_ok = False
    quote_detail: dict[str, Any]
    if quote_source == "schwab" and stamp:
        try:
            observed = dt.datetime.fromisoformat(stamp)
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=dt.timezone.utc)
            result = FreshnessChecker().check_freshness("", observed, mode="swing")
            quote_ok = result.is_executable
            quote_detail = {"status": result.status.value, "age_seconds": result.quote_age_seconds,
                            "reason": result.reason, "observed_at": stamp}
        except ValueError:
            quote_detail = {"status": "UNKNOWN", "age_seconds": None,
                            "reason": "unparseable quote time", "observed_at": stamp}
    else:
        quote_detail = {"status": "UNKNOWN", "age_seconds": None,
                        "reason": ("quote carries no observation time" if quote_source == "schwab"
                                   else f"quote unavailable ({quote_source})"),
                        "observed_at": stamp}

    if bar_source == "schwab" and bar_stamp:
        bar_status = "OBSERVED"
    elif bar_source == "cache":
        bar_status = "CACHE_UNDATED"
    else:
        bar_status = "UNKNOWN"

    overall = "FRESH" if (quote_ok and bar_status == "OBSERVED") else (
        "STALE" if quote_detail["status"] == "STALE_BLOCKED" else (
            "WARN_LATENCY" if quote_detail["status"] == "WARN_LATENCY" else "UNKNOWN"))

    return {
        "overall": overall,
        "quote": quote_detail,
        "bars": {"status": bar_status, "bar_date": bar_stamp, "source": bar_source},
        "is_current": overall == "FRESH",
    }


def _blank_entry(state: str, reason: str, **extra: Any) -> dict[str, Any]:
    payload = {"state": state, "reason": reason, "playbook": None, "direction": None,
               "trigger": None, "invalidation": None, "target": None,
               "reward_risk": None, "chase_limit": None,
               "study_state": None, "eligibility": None, "signal_age_bars": None,
               "freshness": None}
    payload.update(extra)
    return payload


# --------------------------------------------------------------------------- #
# F23 — study state vs. modelled risk
#
# MASTER AUTO's own exit is a SIGNAL REVERSAL: it leaves a position when price
# crosses back through the wave centre, when the intraday VWAP filter trips, or when
# the EMA stack flips against it. It does NOT exit at the ATR stop or the 1R/2R
# targets — those are computed and displayed but never consulted by the exit branch.
#
# Verified in master_auto.py: `active_stop` is assigned and reported, and appears in
# no condition. The only exits are:
#     elif trade_direction == 1 and call_exit_base:  trade_direction = 0
#     elif trade_direction == -1 and put_exit_base:  trade_direction = 0
#
# So a displayed "invalidation" is a REFERENCE level, not a protected order. Showing
# it beside a live plan without saying so overstates what the system does. This
# module keeps the study's own behaviour intact (parity is the point) and labels the
# risk layer honestly, including whether the reference has already been breached.
# --------------------------------------------------------------------------- #

STUDY_EXIT_RULE = (
    "MASTER AUTO exits on a signal reversal: close crosses back through the wave "
    "centre, the intraday VWAP filter trips, or the EMA stack flips against the "
    "position. It does NOT exit at the ATR stop or the 1R/2R targets."
)

INVALIDATION_BASIS_REFERENCE = "REFERENCE_ONLY"
INVALIDATION_BASIS_ENFORCED = "ENFORCED"

REFERENCE_RISK_NOTE = (
    "This level is a REFERENCE computed from ATR. The study will not exit here, so "
    "it is not a protected stop. Treat it as a risk yardstick, not a guarantee."
)

# --------------------------------------------------------------------------- #
# SHORT-SIDE EXPECTANCY — measured, not assumed.
#
# The short conditions in master_auto are line-for-line symmetric with the long
# ones (L415-510), so this is not an implementation defect. A 2-year backtest
# over 400 symbols / 945 short trades puts the short side at -0.60 R per trade
# (PF 0.53), against +0.41 R for the long side (PF 1.37) on the same bars.
#
# A mirror test isolates the cause: negating every long trade's return gives
# -0.41 R, so actual shorts underperform a pure mirror by 0.19 R. That gap is
# market drift, not signal quality. Equal-weight drift over the window was +38%
# and 68% of symbols rose.
#
# A regime gate ("short only while the market is below its 50-day mean") was
# TESTED AND REJECTED: it made shorts worse (-0.87 R, PF 0.39) and helped in
# only 1 of 4 folds, because a breached moving average is a LAGGING signal that
# selects the moment a bounce is most likely. Across seven buckets of market
# position, six were negative and the best was +0.01 R.
#
# So the short side is not tunable into profitability on this evidence. It is
# retained (a sustained bear market could invert the finding) but presented as
# unproven rather than as a peer of the long signals.
# --------------------------------------------------------------------------- #

SHORT_SIDE_STATUS = "UNPROVEN"
SHORT_SIDE_BASIS = "NEGATIVE_EXPECTANCY_MEASURED"

SHORT_SIDE_NOTE = (
    "Short signals are shown for completeness but are NOT validated. Over a "
    "2-year backtest they returned -0.60 R per trade (profit factor 0.53) while "
    "the long side returned +0.41 R (1.37). The logic is symmetric with the long "
    "side, so this is market drift rather than a bug: a regime gate that allowed "
    "shorts only in falling markets was tested and made results worse. Treat "
    "bearish rows as informational, not as tradeable setups."
)


def _stop_breach_state(bars: list[dict] | None, direction: str | None,
                       stop: float | None) -> dict[str, Any]:
    """Has the reference level already been breached on completed bars?

    Purely descriptive: it reports what the price series did relative to the level,
    without claiming the study acted on it.
    """
    if not bars or stop is None or direction not in ("LONG", "SHORT"):
        return {"evaluated": False, "breached": None, "closes_beyond": 0, "lookback": 0}

    window = bars[-20:]
    closes = [b.get("close") for b in window if b.get("close") is not None]
    if not closes:
        return {"evaluated": False, "breached": None, "closes_beyond": 0, "lookback": 0}

    if direction == "LONG":
        beyond = [c for c in closes if c <= stop]
    else:
        beyond = [c for c in closes if c >= stop]

    return {
        "evaluated": True,
        "breached": bool(beyond),
        "breached_on_latest_close": bool(
            (direction == "LONG" and closes[-1] <= stop)
            or (direction == "SHORT" and closes[-1] >= stop)),
        "closes_beyond": len(beyond),
        "lookback": len(closes),
        "note": (f"{len(beyond)} of the last {len(closes)} completed closes are beyond "
                 f"the reference level" if beyond else
                 f"none of the last {len(closes)} completed closes are beyond the "
                 f"reference level"),
    }


def _annotate_risk(payload: dict[str, Any], row: dict[str, Any],
                   bars: list[dict] | None) -> dict[str, Any]:
    """Attach an honest risk description to EVERY entry payload (F23)."""
    direction = payload.get("direction")
    stop = payload.get("invalidation")
    payload["study_exit_rule"] = STUDY_EXIT_RULE
    # Short-side honesty: every payload says whether the direction is validated,
    # so the UI never has to infer it and cannot present shorts as proven.
    if direction == "SHORT":
        payload["side_status"] = SHORT_SIDE_STATUS
        payload["side_basis"] = SHORT_SIDE_BASIS
        payload["side_note"] = SHORT_SIDE_NOTE
    else:
        payload["side_status"] = "MEASURED"
        payload["side_basis"] = None
        payload["side_note"] = None
    if stop is None:
        payload["invalidation_basis"] = None
        payload["risk_note"] = "no reference level computed for this setup"
        payload["stop_breach"] = {"evaluated": False, "breached": None,
                                  "closes_beyond": 0, "lookback": 0}
        return payload
    payload["invalidation_basis"] = INVALIDATION_BASIS_REFERENCE
    payload["risk_note"] = REFERENCE_RISK_NOTE
    payload["stop_breach"] = _stop_breach_state(bars, direction, stop)
    return payload


def classify_entry(row: dict[str, Any], snapshot: Any, cfg: dict[str, Any],
                   *, bars_since_signal: int | None = None,
                   bars: list[dict] | None = None) -> dict[str, Any]:
    """Current ENTRY ELIGIBILITY, with an honest risk annotation (F23).

    Delegates to the core classifier and then labels the risk layer, so every return
    path is annotated exactly once and none can silently claim an enforced stop.
    """
    return _annotate_risk(
        _classify_entry_core(row, snapshot, cfg, bars_since_signal=bars_since_signal),
        row, bars)


def _classify_entry_core(row: dict[str, Any], snapshot: Any, cfg: dict[str, Any],
                         *, bars_since_signal: int | None = None) -> dict[str, Any]:
    """Current ENTRY ELIGIBILITY, separate from the study's own latched state.

    Fixes reviewer F01 (a chased/expired latch is not readiness), F02 (side-aware
    triggers and level ordering), F03 (side-aware extension) and F13 (direction
    must agree between plan and candidate).
    """
    if snapshot is None or not getattr(snapshot, "warmup_ok", False):
        return _blank_entry(ENTRY_BLOCKED_DATA, "insufficient history for the entry engine")

    price = row.get("price")
    if price is None:
        return _blank_entry(ENTRY_BLOCKED_DATA, "no price")

    # F14/F06 gate: readiness requires a verifiable observation time. A row whose
    # freshness is UNKNOWN (cache-backed, undated) may be BROWSED but is never
    # promoted to current readiness.
    freshness = row.get("freshness") or {}
    if freshness and not freshness.get("is_current", False):
        state = ENTRY_PULLBACK if freshness.get("overall") in ("STALE", "WARN_LATENCY") else ENTRY_BLOCKED_DATA
        return _blank_entry(
            state,
            f"data freshness {freshness.get('overall', 'UNKNOWN')} — not currently actionable: "
            f"{((freshness.get('quote') or {}).get('reason') or 'observation time unavailable')}",
            freshness=freshness, eligibility=ELIGIBILITY_EXPIRED,
            direction=row.get("direction"))

    atr = getattr(snapshot, "trade_atr", None)
    latched = getattr(snapshot, "trade_direction", 0) or 0
    study_state = None
    if latched != 0 and getattr(snapshot, "active_stop", None) is not None:
        study_state = STUDY_SIGNAL
    elif getattr(snapshot, "call_ready", False) or getattr(snapshot, "put_ready", False):
        study_state = ENTRY_BREAKOUT
    elif getattr(snapshot, "bull_build", False) or getattr(snapshot, "bear_build", False):
        study_state = ENTRY_PULLBACK

    direction, why = _proposed_direction(snapshot)
    if direction is None:
        if why == "AMBIGUOUS":
            return _blank_entry(ENTRY_BLOCKED_AMBIGUOUS,
                                "simultaneous long and short evidence — blocked, not guessed",
                                study_state=study_state)
        # No qualifying condition. A latched study trade may still exist for
        # research, but it is NOT current readiness.
        if study_state == STUDY_SIGNAL:
            return _blank_entry(ENTRY_EXTENDED,
                                "study position latched but no current entry condition",
                                study_state=study_state,
                                eligibility=ELIGIBILITY_EXPIRED)
        return _blank_entry(ENTRY_EXTENDED if (getattr(snapshot, "bull_stack", False)
                                               or getattr(snapshot, "bear_stack", False))
                            else ENTRY_NONE,
                            "no qualifying structure", study_state=study_state)

    if not atr:
        return _blank_entry(ENTRY_BLOCKED_DATA, "no ATR for plan construction",
                            direction=direction, study_state=study_state)

    trigger = (getattr(snapshot, "call_trigger_price", None) if direction == "LONG"
               else getattr(snapshot, "put_trigger_price", None))
    if trigger is None:
        trigger = (getattr(snapshot, "wave_high", None) if direction == "LONG"
                   else getattr(snapshot, "wave_low", None))
    if trigger is None:
        return _blank_entry(ENTRY_BLOCKED_DATA, "no structural trigger available",
                            direction=direction, study_state=study_state)

    plan = long_plan(trigger, atr, cfg) if direction == "LONG" else short_plan(trigger, atr, cfg)

    # --- a latched study position: only CURRENT if fresh, unfilled and inside the window
    if study_state == STUDY_SIGNAL:
        if latched != (1 if direction == "LONG" else -1):
            return _blank_entry(ENTRY_BLOCKED_AMBIGUOUS,
                                "study direction and current condition disagree",
                                direction=direction, study_state=study_state,
                                eligibility=ELIGIBILITY_INVALIDATED)
        max_age = cfg.get("signal_max_age_bars")
        if bars_since_signal is not None and max_age is not None and bars_since_signal > max_age:
            return _blank_entry(ENTRY_EXTENDED,
                                f"signal is {bars_since_signal} bars old (max {max_age}) — expired entry",
                                direction=direction, study_state=study_state,
                                eligibility=ELIGIBILITY_EXPIRED,
                                signal_age_bars=bars_since_signal)
        stop = getattr(snapshot, "active_stop", None)
        if stop is not None and ((direction == "LONG" and price <= stop)
                                 or (direction == "SHORT" and price >= stop)):
            # F23: say "reference level", not "study stop" — the study does not exit
            # here, so calling it a stop overstates what the system does.
            return _blank_entry(ENTRY_EXTENDED,
                                "price is beyond the reference level — thesis invalidated "
                                "(the study itself does not exit at this level)",
                                direction=direction, study_state=study_state,
                                eligibility=ELIGIBILITY_INVALIDATED,
                                signal_age_bars=bars_since_signal)
        extended, _ = _extension_state(plan, price)
        if extended:
            return _blank_entry(ENTRY_EXTENDED,
                                "price is beyond the chase limit — do not chase a latched study entry",
                                direction=direction, study_state=study_state,
                                eligibility=ELIGIBILITY_EXPIRED,
                                signal_age_bars=bars_since_signal,
                                trigger=plan["trigger"], chase_limit=plan["chase_limit"],
                                invalidation=getattr(snapshot, "active_stop", None),
                                target=getattr(snapshot, "active_target2", None))
        return {
            "state": ENTRY_TRIGGER,
            "reason": "study position is current, unfilled and inside the entry window",
            "playbook": "qx_master_auto_fast", "direction": direction,
            "trigger": plan["trigger"], "invalidation": stop, "target": plan["target"],
            "reward_risk": plan["reward_risk"], "chase_limit": plan["chase_limit"],
            "reward_risk_basis": plan.get("reward_risk_basis"),
            "reward_risk_note": plan.get("reward_risk_note"),
            "realised_mean_r": plan.get("realised_mean_r"),
            "study_state": study_state, "eligibility": ELIGIBILITY_READY,
            "signal_age_bars": bars_since_signal,
        }

    # --- breakout watch: structure present, entry candle not yet printed
    if study_state == ENTRY_BREAKOUT:
        payload = dict(plan)
        payload.update({
            "state": ENTRY_BREAKOUT,
            "reason": "regime + wave breakout + volume, awaiting the entry candle",
            "playbook": "qx_master_auto_fast",
            "study_state": study_state, "eligibility": ELIGIBILITY_READY,
            "signal_age_bars": bars_since_signal,
        })
        return payload

    # --- pullback / near-trigger
    if study_state == ENTRY_PULLBACK:
        distance = abs(trigger - price) / atr if atr else None
        near = distance is not None and distance <= cfg["near_trigger_atr"]
        payload = dict(plan)
        payload.update({
            "state": ENTRY_BREAKOUT if near else ENTRY_PULLBACK,
            "reason": (f"within {distance:.2f} ATR of the trigger" if near
                       else "building inside the structure; pullback candidate"),
            "playbook": "qx_master_auto_fast",
            "study_state": study_state, "eligibility": ELIGIBILITY_READY,
            "signal_age_bars": bars_since_signal,
        })
        return payload

    return _blank_entry(ENTRY_NONE, "no qualifying structure",
                        direction=direction, study_state=study_state)


def _extension_state(entry: dict[str, Any], price: float | None) -> tuple[bool, float | None]:
    """Is price beyond the chase limit? Side-aware (reviewer F03).

    Returns ``(extended, price_distance)`` where the distance is a PRICE distance,
    named for what it is. A LONG is extended above its limit; a SHORT below.
    """
    limit = entry.get("chase_limit")
    direction = entry.get("direction")
    if limit is None or price is None or direction is None:
        return False, None
    if direction == "LONG":
        return price > limit, round(price - limit, 4)
    if direction == "SHORT":
        return price < limit, round(limit - price, 4)
    return False, None


# --------------------------------------------------------------------------- #
# Breadth — denominator and weight coverage are mandatory
# --------------------------------------------------------------------------- #

def _breadth(rows: list[dict[str, Any]], universe: str) -> dict[str, Any]:
    """Breadth with an honest denominator (reviewer F11).

    The denominator is every member the universe returned. Members whose states
    could not be computed are counted as MISSING rather than dropped, so a partial
    view can never read as complete coverage.
    """
    denominator = len(rows)
    classified = [r for r in rows if r.get("momentum") and r.get("trend") and r.get("history_ok")]
    missing = denominator - len(classified)
    trend_up = [r for r in classified if r["trend"] == momo_trend.BULLISH]
    aligned = [r for r in classified
               if r["momentum"] == momo_trend.BULLISH and r["trend"] == momo_trend.BULLISH]

    weighted = None
    weight_covered_pct = None
    if universe == membership.UNIVERSE_HOLDINGS:
        total_weight = sum(r.get("weight") or 0.0 for r in rows)
        classified_weight = sum(r.get("weight") or 0.0 for r in classified)
        if total_weight:
            aligned_weight = sum(r.get("weight") or 0.0 for r in aligned)
            weighted = round(aligned_weight / total_weight, 4)
            weight_covered_pct = round(classified_weight / total_weight * 100.0, 2)

    return {
        "universe": universe,
        "denominator": denominator,
        "covered": len(classified),
        "missing_data": missing,
        "trend_up_pct": round(len(trend_up) / len(classified), 4) if classified else None,
        "aligned_pct": round(len(aligned) / len(classified), 4) if classified else None,
        "equal_weight": True,
        "holdings_weighted_aligned_pct": weighted,
        "weight_covered_pct": weight_covered_pct,
        "denominator_note": (
            f"{denominator} member(s) in the universe; {len(classified)} classified, "
            f"{missing} missing data and counted as missing (not excluded). "
            "Breadth is computed BEFORE display filters."
        ),
    }


# --------------------------------------------------------------------------- #
# Main exploration
# --------------------------------------------------------------------------- #

def explore(symbol: str, universe: str = membership.UNIVERSE_HOLDINGS,
            *, timeframe: str = "1d", config: dict[str, Any] | None = None,
            view: str = "aligned_up", limit: int = 120) -> dict[str, Any]:
    """Explore one sector/industry ETF and classify its members.

    Reviewer F08: the requested timeframe is APPLIED to the bar fetch and to the
    entry engine, never merely echoed back. An unsupported timeframe is rejected
    rather than silently computed on daily data.
    """
    cfg = _config(config)
    symbol = symbol.strip().upper()
    market = MarketData()

    interval = _normalise_interval(timeframe)
    if interval is None:
        raise ValueError(
            f"unsupported timeframe {timeframe!r}; supported: '1d' (swing) or "
            f"'1m'/'5m'/'15m'/'30m' (intraday). Refusing to compute on a different "
            f"timeframe than requested.")
    minutes = 1440 if interval == "1d" else int(interval.rstrip("m"))

    parent_bars, parent_source = market.bars(symbol, interval=interval)
    benchmark_bars, benchmark_source = market.bars(cfg["benchmark"], interval=interval)
    parent_quote, parent_quote_source = market.quote(symbol)

    membership_result = membership.resolve_universe(symbol, universe)
    parent_phase = market_phases.latest(parent_bars) if parent_bars else None
    parent_momo = momo_trend.latest(parent_bars) if parent_bars else None

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for holding in membership_result.rows:
        try:
            bars, source = market.bars(holding.symbol, interval=interval)
            if not bars:
                rows.append(_empty_row(holding, "no price data"))
                continue
            history_ok = len(bars) >= cfg["min_history_bars"]
            momo = momo_trend.latest(bars)
            phase = market_phases.latest(bars)
            master = master_auto.latest(bars)
            track = momo_trend.transition_track(momo_trend.evaluate_series(
                [b["high"] for b in bars], [b["low"] for b in bars], [b["close"] for b in bars])) if bars else {}

            quote, quote_source = market.quote(holding.symbol)
            price = (quote or {}).get("last") or bars[-1]["close"]
            entry = classify_entry({"price": price}, master, cfg, bars=bars)
            extended, over = _extension_state(entry, price)

            rows.append({
                "symbol": holding.symbol,
                "company": holding.name,
                "weight": holding.weight,
                "rank": holding.rank,
                "price": round(price, 4) if price else None,
                "price_source": quote_source,
                "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
                # F06: observation time vs retrieval time are now distinct.
                "observed_at": (quote or {}).get("timestamp"),
                "bar_date": bars[-1].get("date"),
                "bar_completed": bars[-1].get("bar_completed"),
                "freshness": _freshness(quote, bars, quote_source, source),
                "bar_source": source,
                "history_ok": history_ok,
                "bars": len(bars),
                "momentum": momo.momentum if (momo and history_ok) else None,
                "trend": momo.trend if (momo and history_ok) else None,
                "aligned_up": bool(momo and history_ok and momo.aligned_up),
                "aligned_down": bool(momo and history_ok and momo.aligned_down),
                "bars_since_alignment": track.get("bars_since_alignment") if track else None,
                "previous_state": track.get("previous_state") if track else None,
                "newly_aligned": bool(track.get("newly_aligned")) if track else False,
                "lost_alignment": bool(track.get("lost_alignment")) if track else False,
                "phase": phase.phase if phase else None,
                "phase_label": phase.description if phase else None,
                "rule_version": momo_trend.RULE_VERSION if momo else None,
                "rs_vs_parent": {f"{h}d": _relative(bars, parent_bars, h) for h in (5, 20, 60)},
                "rs_vs_market": {f"{h}d": _relative(bars, benchmark_bars, h) for h in (5, 20, 60)},
                "rs_basis": _relative_basis(bars, parent_bars),
                "entry": entry,
                "extended": extended,
                "over_chase_limit_by": over,
                "master_state": master.price_state if master else None,
                "setup_label": master.setup_label if master else None,
                "rvol": master.rvol_display if master else None,
                "momentum_up_and_trend_up": bool(momo and history_ok and momo.aligned_up),
                # F12: declared so the Pullback view's rule is inspectable, and so a
                # caller can see WHY a row is in it.
                "is_pullback": _is_pullback({
                    "aligned_down": bool(momo and history_ok and momo.aligned_down),
                    "trend": momo.trend if (momo and history_ok) else None,
                    "momentum": momo.momentum if (momo and history_ok) else None,
                    "history_ok": history_ok,
                    "phase": phase.phase if phase else None,
                }),
                "phase_warning": bool(phase and phase.warning),
            })
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not kill the sector
            errors.append(f"{holding.symbol}: {type(exc).__name__}: {str(exc)[:80]}")
            rows.append(_empty_row(holding, "lookup failed"))

    breadth = _breadth(rows, universe)
    views = _views(rows)
    filtered = _apply_view(rows, view)[:limit]

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "symbol": symbol,
        "universe": universe,
        "timeframe": timeframe,
        "parent": {
            "symbol": symbol,
            "price": (parent_quote or {}).get("last"),
            "change_pct": (parent_quote or {}).get("change_pct"),
            "bar_source": parent_source,
            "quote_source": parent_quote_source,
            "momentum": parent_momo.momentum if parent_momo else None,
            "trend": parent_momo.trend if parent_momo else None,
            "aligned_up": bool(parent_momo and parent_momo.aligned_up),
            "phase": parent_phase.phase if parent_phase else None,
            "phase_label": parent_phase.description if parent_phase else None,
            "bars": len(parent_bars),
            "completed_bar": parent_bars[-1] if parent_bars else None,
        },
        "membership": membership_result.as_dict() | {"rows": None},
        "membership_rows": membership_result.count,
        "breadth": breadth,
        "views": views,
        "pullback_definition": PULLBACK_DEFINITION,
        "view": view,
        "rows": filtered,
        "row_count": len(rows),
        "shown": len(filtered),
        "errors": errors,
        "benchmark": {"symbol": cfg["benchmark"], "source": benchmark_source},
        "rules": {
            "momo_trend": momo_trend.RULE_VERSION,
            "phases": market_phases.RULE_VERSION,
            "entry": master_auto.RULE_VERSION,
        },
        "warnings": _warnings(membership_result, rows),
    }


def _empty_row(holding: membership.HoldingRow, reason: str) -> dict[str, Any]:
    return {
        "symbol": holding.symbol, "company": holding.name, "weight": holding.weight,
        "rank": holding.rank, "price": None, "history_ok": False, "bars": 0,
        "momentum": None, "trend": None, "aligned_up": False, "aligned_down": False,
        "bars_since_alignment": None, "previous_state": None, "newly_aligned": False,
        "lost_alignment": False, "phase": None, "phase_label": None, "rule_version": None,
        "rs_vs_parent": {}, "rs_vs_market": {}, "error": reason,
        "entry": {"state": ENTRY_BLOCKED_DATA, "reason": reason, "playbook": None,
                  "trigger": None, "invalidation": None, "target": None,
                  "reward_risk": None, "chase_limit": None},
        "extended": False, "over_chase_limit_by": None, "momentum_up_and_trend_up": False,
    }


VIEWS = (
    ("aligned_up", "Momentum UP & Trend UP", "the default qualified view"),
    ("all", "All members", "everything in the universe"),
    ("newly_aligned", "Newly aligned", "alignment began on the latest bar"),
    ("established", "Established leaders", "aligned for 20+ bars"),
    ("pullback", "Pullback watch", "healthy uptrend losing short-term momentum (Boyd phase 4)"),
    ("recovery", "Recovery / reversal watchlist", "phase 2 emerging from a downtrend"),
    ("bearish", "Bearish aligned", "momentum down and trend down"),
    ("insufficient", "Insufficient data", "not enough history to classify"),
)

# F12: what qualifies as a PULLBACK WATCH.
#
# The previous rule asked for `trend == BULLISH and momentum != BULLISH`, which is
# mathematically IMPOSSIBLE in TOPS-MultiTrend: a bullish Trend requires the bullish
# EMA8>EMA13>EMA21 stack, and that same stack is what defines bullish Momo. The view
# could therefore never populate.
#
# A pullback is instead defined by a DIFFERENT study that already measures it: Boyd
# Phase 4 is literally "strong uptrend that has lost Hull momentum" — a subset of
# phase 3, tested first. We require:
#   * Boyd Phase 4 (the study's own pullback-warning state), OR
#   * Trend UP with Momo not-yet-UP, kept for completeness (can occur when a bullish
#     wave is present without the full EMA stack ordering).
# In BOTH cases the name must still be structurally healthy: it is not bearish, and
# it is not below its own established trend.
PULLBACK_DEFINITION = (
    "Boyd phase 4 (uptrend losing Hull momentum), or Trend UP with Momo not yet UP; "
    "never bearish, and never a broken structure"
)


def _is_pullback(row: dict[str, Any]) -> bool:
    if row.get("aligned_down") or row.get("trend") == momo_trend.BEARISH:
        return False
    if not row.get("history_ok"):
        return False
    if row.get("phase") == 4:
        return True
    return row.get("trend") == momo_trend.BULLISH and row.get("momentum") != momo_trend.BULLISH


def _apply_view(rows: list[dict[str, Any]], view: str) -> list[dict[str, Any]]:
    if view == "all":
        return rows
    if view == "aligned_up":
        return [r for r in rows if r.get("momentum_up_and_trend_up")]
    if view == "newly_aligned":
        return [r for r in rows if r.get("newly_aligned")]
    if view == "established":
        return [r for r in rows if r.get("aligned_up") and (r.get("bars_since_alignment") or 0) >= 20]
    if view == "pullback":
        return [r for r in rows if _is_pullback(r)]
    if view == "recovery":
        return [r for r in rows if r.get("phase") == 2]
    if view == "bearish":
        return [r for r in rows if r.get("aligned_down")]
    if view == "insufficient":
        return [r for r in rows if not r.get("history_ok")]
    return rows


def _views(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": vid, "label": label, "description": desc, "count": len(_apply_view(rows, vid))}
            for vid, label, desc in VIEWS]


def _warnings(membership_result: membership.MembershipResult,
              rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    if membership_result.status != "OK":
        out.append(f"membership status: {membership_result.status}")
    if membership_result.warning:
        out.append(membership_result.warning)
    if membership_result.is_partial:
        out.append("PARTIAL UNIVERSE — these rows do not represent the whole fund; "
                   "breadth is biased toward large holdings.")
    missing = sum(1 for r in rows if not r.get("history_ok"))
    if missing:
        out.append(f"{missing} member(s) lack sufficient history and are excluded from breadth.")
    return out
