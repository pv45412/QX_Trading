"""Point-in-time trade simulation using the REAL studies, not a reimplementation.

Why this matters: a backtest that reimplements the rules tests the reimplementation.
This module calls ``master_auto.evaluate_series`` — the same code the live app runs —
so a result here is a statement about the shipped rules.

Lookahead discipline
--------------------
* A signal seen on the CLOSE of bar *i* is executed at the **open of bar i+1**.
  Entering on the signal bar's own close would be optimistic and is not what a live
  trader can do.
* ``verify_causality`` checks that the snapshot at index *i*, computed from the full
  series, equals the snapshot computed from only ``bars[:i+1]``. If any indicator were
  non-causal this test would fail, which is the only real proof of no lookahead.

Two exit policies, because the live app displays an ATR stop the study does not honour
(reviewer F23):
* ``STUDY`` — exit only when the study's own direction latch clears.
* ``STOP``  — exit at the ATR stop when price reaches it, else the study exit.
Comparing them answers a live design question with numbers instead of opinion.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Iterable

import qx.explorer.master_auto as master_auto

EXIT_STUDY = "STUDY_EXIT"
EXIT_STOP = "STOP_HIT"
EXIT_STOP_GAP = "STOP_GAPPED"
EXIT_END = "END_OF_DATA"
EXIT_OPEN = "STILL_OPEN"

# Per-side friction. Kept explicit and small; the point is that it is not zero.
DEFAULT_COST_BPS = 2.0


@dataclass
class Trade:
    symbol: str
    direction: str
    entry_index: int
    entry_date: str | None
    entry_price: float
    exit_index: int
    exit_date: str | None
    exit_price: float
    exit_reason: str
    initial_risk: float          # per-share risk at entry (ATR x multiplier)
    r_multiple: float
    mae_r: float                 # worst adverse excursion, in R (negative or 0)
    mfe_r: float                 # best favourable excursion, in R
    bars_held: int
    gross_pnl: float
    costs: float
    net_pnl: float
    net_r: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "direction": self.direction,
            "entry_date": self.entry_date, "entry_price": round(self.entry_price, 4),
            "exit_date": self.exit_date, "exit_price": round(self.exit_price, 4),
            "exit_reason": self.exit_reason, "bars_held": self.bars_held,
            "initial_risk": round(self.initial_risk, 4),
            "r_multiple": round(self.r_multiple, 3),
            "net_r": round(self.net_r, 3),
            "mae_r": round(self.mae_r, 3), "mfe_r": round(self.mfe_r, 3),
            "net_pnl": round(self.net_pnl, 2),
        }


@dataclass
class SimResult:
    symbol: str
    trades: list[Trade] = field(default_factory=list)
    bars: int = 0
    error: str | None = None


def verify_causality(bars: list[dict[str, Any]], *, samples: int = 8) -> dict[str, Any]:
    """Prove the study is causal: snapshot[i] must not depend on bars after i.

    Computed one way from the full series and another from a truncated prefix. If the
    two disagree at any sampled index, the study is reading the future and any
    backtest built on it is invalid.
    """
    if len(bars) < 60:
        return {"ok": False, "reason": "too few bars"}
    full = {snap.index: snap for snap in master_auto.evaluate_series(bars, minutes=1440)}
    indices = sorted({int(len(bars) * (k + 1) / (samples + 1)) for k in range(samples)})
    mismatches: list[dict[str, Any]] = []
    for index in indices:
        prefix = bars[: index + 1]
        prefix_series = master_auto.evaluate_series(prefix, minutes=1440)
        if not prefix_series:
            continue
        truncated = prefix_series[-1]
        reference = full.get(index)
        if reference is None:
            continue
        for field_name in ("trade_direction", "bias_state", "price_state",
                           "call_ready", "put_ready"):
            if getattr(reference, field_name, None) != getattr(truncated, field_name, None):
                mismatches.append({
                    "index": index, "field": field_name,
                    "full_series": getattr(reference, field_name, None),
                    "prefix_only": getattr(truncated, field_name, None),
                })
    return {
        "ok": not mismatches,
        "checked_indices": indices,
        "mismatches": mismatches[:10],
        "note": ("causal: the study reads only past bars" if not mismatches else
                 "NON-CAUSAL: the study reads future bars — backtest invalid"),
    }


def _cost(price: float, quantity: float, bps: float) -> float:
    return abs(price * quantity) * (bps / 10000.0)


def simulate_symbol(bars: list[dict[str, Any]], *, symbol: str,
                    exit_policy: str = EXIT_STUDY,
                    atr_stop_multiplier: float = 1.10,
                    cost_bps: float = DEFAULT_COST_BPS,
                    quantity: float = 100.0) -> SimResult:
    """Walk one symbol bar by bar and record completed trades."""
    result = SimResult(symbol=symbol, bars=len(bars))
    if len(bars) < 160:
        result.error = "insufficient history"
        return result

    try:
        snapshots = {snap.index: snap for snap in
                     master_auto.evaluate_series(bars, minutes=1440)}
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    position: dict[str, Any] | None = None
    last = len(bars) - 1

    for index in range(last):
        snap = snapshots.get(index)
        if snap is None:
            continue
        execution = bars[index + 1]           # signals act on the NEXT bar
        direction = getattr(snap, "trade_direction", 0) or 0
        atr = getattr(snap, "trade_atr", None)

        # ---------------- manage an open position ----------------
        if position is not None:
            hit_stop = False
            exit_price = execution["open"]
            reason = EXIT_STUDY

            if exit_policy == EXIT_STOP:
                stop = position["stop"]
                if position["direction"] == "LONG":
                    if execution["open"] <= stop:
                        hit_stop, exit_price, reason = True, execution["open"], EXIT_STOP_GAP
                    elif execution["low"] <= stop:
                        hit_stop, exit_price, reason = True, stop, EXIT_STOP
                else:
                    if execution["open"] >= stop:
                        hit_stop, exit_price, reason = True, execution["open"], EXIT_STOP_GAP
                    elif execution["high"] >= stop:
                        hit_stop, exit_price, reason = True, stop, EXIT_STOP

            study_closed = (direction == 0)
            if hit_stop or study_closed:
                if not hit_stop:
                    reason = EXIT_STUDY
                result.trades.append(_close(position, index + 1, bars, exit_price,
                                            reason, quantity, cost_bps))
                position = None
            else:
                _update_excursions(position, execution)
            continue

        # ---------------- look for an entry ----------------
        if direction == 0 or not atr or atr <= 0:
            continue
        side = "LONG" if direction == 1 else "SHORT"
        entry_price = execution["open"]
        stop = (entry_price - atr * atr_stop_multiplier if side == "LONG"
                else entry_price + atr * atr_stop_multiplier)
        risk = abs(entry_price - stop)
        if risk <= 0:
            continue
        position = {
            "direction": side, "entry_index": index + 1,
            "entry_date": execution.get("date"), "entry_price": entry_price,
            "stop": stop, "risk": risk, "atr": atr,
            "mae": 0.0, "mfe": 0.0,
        }
        _update_excursions(position, execution)

    if position is not None:
        final = bars[last]
        result.trades.append(_close(position, last, bars, final["close"], EXIT_END,
                                    quantity, cost_bps))
    return result


def _update_excursions(position: dict[str, Any], bar: dict[str, Any]) -> None:
    """Track the worst and best excursion in R terms, using the bar's own range."""
    risk = position["risk"]
    if risk <= 0:
        return
    if position["direction"] == "LONG":
        adverse = (position["entry_price"] - bar["low"]) / risk
        favourable = (bar["high"] - position["entry_price"]) / risk
    else:
        adverse = (bar["high"] - position["entry_price"]) / risk
        favourable = (position["entry_price"] - bar["low"]) / risk
    position["mae"] = min(position["mae"], -abs(adverse) if adverse > 0 else 0.0)
    position["mfe"] = max(position["mfe"], favourable)


def _close(position: dict[str, Any], exit_index: int, bars: list[dict[str, Any]],
           exit_price: float, reason: str, quantity: float, cost_bps: float) -> Trade:
    entry = position["entry_price"]
    risk = position["risk"]
    if position["direction"] == "LONG":
        gross = (exit_price - entry) * quantity
    else:
        gross = (entry - exit_price) * quantity
    costs = _cost(entry, quantity, cost_bps) + _cost(exit_price, quantity, cost_bps)
    net = gross - costs
    net_r = net / (risk * quantity) if risk and quantity else 0.0
    r_multiple = ((exit_price - entry) if position["direction"] == "LONG"
                  else (entry - exit_price)) / risk if risk else 0.0
    return Trade(
        symbol="", direction=position["direction"],
        entry_index=position["entry_index"], entry_date=position["entry_date"],
        entry_price=entry, exit_index=exit_index,
        exit_date=bars[exit_index].get("date"), exit_price=exit_price,
        exit_reason=reason, initial_risk=risk,
        r_multiple=r_multiple, mae_r=position["mae"], mfe_r=position["mfe"],
        bars_held=exit_index - position["entry_index"],
        gross_pnl=gross, costs=costs, net_pnl=net, net_r=net_r,
    )


def simulate_universe(universe: dict[str, list[dict[str, Any]]], *,
                      exit_policy: str = EXIT_STUDY,
                      atr_stop_multiplier: float = 1.10,
                      cost_bps: float = DEFAULT_COST_BPS,
                      quantity: float = 100.0,
                      progress: Any = None) -> dict[str, Any]:
    """Run the simulation across a universe of bar sets."""
    all_trades: list[Trade] = []
    errors: list[str] = []
    for done, (symbol, bars) in enumerate(universe.items(), start=1):
        outcome = simulate_symbol(bars, symbol=symbol, exit_policy=exit_policy,
                                  atr_stop_multiplier=atr_stop_multiplier,
                                  cost_bps=cost_bps, quantity=quantity)
        for trade in outcome.trades:
            trade.symbol = symbol
            all_trades.append(trade)
        if outcome.error:
            errors.append(f"{symbol}: {outcome.error}")
        if progress and done % 25 == 0:
            progress(done, len(universe))
    return {
        "exit_policy": exit_policy,
        "symbols": len(universe),
        "trades": all_trades,
        "trade_count": len(all_trades),
        "errors": errors[:20],
        "error_count": len(errors),
        "cost_bps_per_side": cost_bps,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
