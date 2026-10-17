"""Backtest statistics, reported so that a weak result cannot look strong.

Design rules:
* Every aggregate is reported with the sample size it was computed from.
* Percentiles are used rather than means alone, because trade R-multiples are
  skewed and a mean hides the tail that actually hurts.
* The MAE distribution is a first-class output: it answers whether the displayed
  ATR stop (which the study does NOT honour — reviewer F23) is survivable.
* Buy-and-hold is reported alongside, because a strategy that cannot beat holding
  the index has not earned its complexity.
"""
from __future__ import annotations

from typing import Any, Sequence


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = fraction * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return round(ordered[low] * (1 - weight) + ordered[high] * weight, 3)


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def max_drawdown_r(trades: Sequence[Any]) -> dict[str, Any]:
    """Peak-to-trough drawdown over the cumulative R curve, in trade order."""
    if not trades:
        return {"max_drawdown_r": None, "trough_after_peak": None}
    ordered = sorted(trades, key=lambda t: (t.exit_date or "", t.exit_index))
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for trade in ordered:
        equity += trade.net_r
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return {"max_drawdown_r": round(worst, 3), "final_r": round(equity, 3),
            "trades_in_curve": len(ordered)}


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    """Full statistics for one simulation result."""
    trades = list(result.get("trades") or [])
    if not trades:
        return {
            "exit_policy": result.get("exit_policy"),
            "symbols": result.get("symbols"),
            "trade_count": 0,
            "verdict": "NO_TRADES",
            "note": ("The rules produced no completed trades over this universe and "
                     "window. That is a finding, not a failure — it means the entry "
                     "conditions rarely coincide with the data available."),
            "errors": result.get("error_count"),
        }

    r_values = [t.net_r for t in trades]
    gross_r = [t.r_multiple for t in trades]
    wins = [r for r in r_values if r > 0]
    losses = [r for r in r_values if r < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))

    mae = [t.mae_r for t in trades]
    mfe = [t.mfe_r for t in trades]

    by_reason: dict[str, int] = {}
    for trade in trades:
        by_reason[trade.exit_reason] = by_reason.get(trade.exit_reason, 0) + 1

    drawdown = max_drawdown_r(trades)
    symbols_traded = len({t.symbol for t in trades})

    return {
        "exit_policy": result.get("exit_policy"),
        "symbols": result.get("symbols"),
        "symbols_traded": symbols_traded,
        "trade_count": len(trades),
        "cost_bps_per_side": result.get("cost_bps_per_side"),

        # --- the number the app currently fakes as a constant 2.0 ---
        "realized_r": {
            "mean": _mean(gross_r),
            "net_mean": _mean(r_values),
            "median": _percentile(gross_r, 0.5),
            "p10": _percentile(gross_r, 0.10),
            "p25": _percentile(gross_r, 0.25),
            "p75": _percentile(gross_r, 0.75),
            "p90": _percentile(gross_r, 0.90),
            "best": round(max(gross_r), 3),
            "worst": round(min(gross_r), 3),
            "note": ("This is what the trades ACTUALLY resolved to. The app displays "
                     "R:R 2.0 as a constant because the study never targets it."),
        },

        "win_rate": round(len(wins) / len(trades), 4),
        "expectancy_r": _mean(r_values),
        "profit_factor": (round(gross_win / gross_loss, 3) if gross_loss > 0
                          else ("infinite" if gross_win > 0 else None)),
        "gross_win_r": round(gross_win, 3),
        "gross_loss_r": round(gross_loss, 3),

        # --- the F23 question: is the displayed stop survivable? ---
        "mae": {
            "mean": _mean(mae),
            "median": _percentile(mae, 0.5),
            "p10": _percentile(mae, 0.10),
            "p05": _percentile(mae, 0.05),
            "worst": round(min(mae), 3) if mae else None,
            "pct_beyond_1r": round(sum(1 for m in mae if m <= -1.0) / len(mae), 4),
            "pct_beyond_2r": round(sum(1 for m in mae if m <= -2.0) / len(mae), 4),
            "note": ("How far trades moved AGAINST the position before the exit "
                     "fired, in R. If a large share exceed 1R, the displayed ATR stop "
                     "would have been hit — and the study does not exit there."),
        },
        "mfe": {
            "mean": _mean(mfe),
            "median": _percentile(mfe, 0.5),
            "p90": _percentile(mfe, 0.90),
            "note": "Best favourable excursion before exit — the headroom that existed.",
        },

        "drawdown": drawdown,
        "exit_reasons": by_reason,
        "bars_held": {
            "mean": _mean([t.bars_held for t in trades]),
            "median": _percentile([t.bars_held for t in trades], 0.5),
            "max": max(t.bars_held for t in trades),
        },
        "errors": result.get("error_count"),
        "generated_at": result.get("generated_at"),
    }


def buy_and_hold(bars_by_symbol: dict[str, list[dict[str, Any]]], *,
                 cost_bps: float = 2.0) -> dict[str, Any]:
    """Equal-weight buy-and-hold over the same window, as an honest baseline."""
    returns: list[float] = []
    for symbol, bars in bars_by_symbol.items():
        if len(bars) < 2:
            continue
        first = bars[0]["close"]
        last = bars[-1]["close"]
        if first <= 0:
            continue
        gross = last / first - 1.0
        costs = 2 * (cost_bps / 10000.0)
        returns.append(gross - costs)
    if not returns:
        return {"symbols": 0, "mean_return": None}
    ordered = sorted(returns)
    return {
        "symbols": len(returns),
        "mean_return": round(sum(returns) / len(returns), 4),
        "median_return": round(ordered[len(ordered) // 2], 4),
        "pct_positive": round(sum(1 for r in returns if r > 0) / len(returns), 4),
        "best": round(max(returns), 4),
        "worst": round(min(returns), 4),
        "note": ("Equal-weight buy-and-hold over the identical window, with the same "
                 "per-side friction. A strategy that cannot beat this has not earned "
                 "its complexity."),
    }


def compare_policies(study: dict[str, Any], stopped: dict[str, Any]) -> dict[str, Any]:
    """Study exit vs stop-enforced — the F23 question answered with numbers."""
    study_r = (study.get("realized_r") or {}).get("net_mean")
    stopped_r = (stopped.get("realized_r") or {}).get("net_mean")
    study_mae = (study.get("mae") or {}).get("p05")
    stopped_mae = (stopped.get("mae") or {}).get("p05")
    verdict = "INCONCLUSIVE"
    if study_r is not None and stopped_r is not None:
        if stopped_r > study_r + 0.05:
            verdict = "STOP_WOULD_HAVE_HELPED"
        elif study_r > stopped_r + 0.05:
            verdict = "STUDY_EXIT_IS_BETTER"
        else:
            verdict = "NO_MATERIAL_DIFFERENCE"
    return {
        "study_exit_net_mean_r": study_r,
        "stop_enforced_net_mean_r": stopped_r,
        "study_exit_p05_mae": study_mae,
        "stop_enforced_p05_mae": stopped_mae,
        "verdict": verdict,
        "note": ("Both variants share identical entries; only the exit differs. This "
                 "is the direct test of whether enforcing the displayed ATR stop "
                 "would improve or damage the system."),
    }
