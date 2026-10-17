"""Parameter sensitivity on the full cleaned universe, one gate at a time.

This does NOT reimplement the rules: it calls master_auto.evaluate_series with a
modified config and feeds the resulting direction latch through the same simulator.
So each row is a statement about the shipped study under a different setting.
"""
import json
import os
import sys
import time

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

import qx.explorer.master_auto as master_auto  # noqa: E402
from qx.backtesting import historical, metrics, simulate  # noqa: E402

universe, _ = historical.build_universe(window="2y")
bars_only = {s: b.bars for s, b in universe.items()}
print(f"universe: {len(bars_only)} symbols", flush=True)

BASE = dict(master_auto.DEFAULTS)


def run(config: dict, label: str) -> dict:
    """Evaluate the study with `config`, then simulate trades on its latch."""
    original = master_auto.DEFAULTS
    trades = []
    errors = 0
    started = time.time()
    try:
        master_auto.DEFAULTS = {**BASE, **config}
        for symbol, bars in bars_only.items():
            snapshots = {s.index: s for s in
                         master_auto.evaluate_series(bars, minutes=1440)}
            last = len(bars) - 1
            position = None
            for index in range(last):
                snap = snapshots.get(index)
                if snap is None:
                    continue
                nxt = bars[index + 1]
                direction = getattr(snap, "trade_direction", 0) or 0
                atr = getattr(snap, "trade_atr", None)
                if position is not None:
                    if direction == 0:
                        trade = simulate._close(position, index + 1, bars, nxt["open"],
                                                simulate.EXIT_STUDY, 100.0, 2.0)
                        trade.symbol = symbol
                        trades.append(trade)
                        position = None
                    else:
                        simulate._update_excursions(position, nxt)
                    continue
                if direction == 0 or not atr or atr <= 0:
                    continue
                side = "LONG" if direction == 1 else "SHORT"
                entry = nxt["open"]
                stop = (entry - atr * 1.10) if side == "LONG" else (entry + atr * 1.10)
                risk = abs(entry - stop)
                if risk <= 0:
                    continue
                position = {"direction": side, "entry_index": index + 1,
                            "entry_date": nxt.get("date"), "entry_price": entry,
                            "stop": stop, "risk": risk, "atr": atr, "mae": 0.0, "mfe": 0.0}
                simulate._update_excursions(position, nxt)
            if position is not None:
                trade = simulate._close(position, last, bars, bars[last]["close"],
                                        simulate.EXIT_END, 100.0, 2.0)
                trade.symbol = symbol
                trades.append(trade)
    except Exception as exc:  # noqa: BLE001
        errors += 1
        print(f"  !! {label}: {type(exc).__name__}: {exc}", flush=True)
    finally:
        master_auto.DEFAULTS = original

    if not trades:
        return {"label": label, "n": 0, "seconds": round(time.time() - started, 1)}
    r = [t.net_r for t in trades]
    wins = [x for x in r if x > 0]
    losses = [x for x in r if x < 0]
    gw = sum(wins)
    gl = abs(sum(losses))
    ordered = sorted(r)
    return {
        "label": label, "n": len(trades), "errors": errors,
        "mean_r": round(sum(r) / len(r), 4),
        "median_r": round(ordered[len(ordered) // 2], 4),
        "win_rate": round(len(wins) / len(r), 4),
        "profit_factor": round(gw / gl, 3) if gl else None,
        "final_r": round(sum(r), 1),
        "seconds": round(time.time() - started, 1),
    }


rows = []
sweeps = [
    ({}, "BASE (as shipped)"),
    ({"min_relative_volume": 1.20}, "RVOL gate 0.90 -> 1.20"),
    ({"min_relative_volume": 1.50}, "RVOL gate 0.90 -> 1.50"),
    ({"min_relative_volume": 2.00}, "RVOL gate 0.90 -> 2.00"),
    ({"use_volume_filter": False}, "volume filter OFF"),
    ({"use_supertrend_bias": False}, "supertrend bias OFF"),
    ({"bias_flip_confirm_bars": 3}, "bias confirm 2 -> 3"),
    ({"bias_flip_confirm_bars": 4}, "bias confirm 2 -> 4"),
    ({"rsi_overbought": 80.0, "rsi_oversold": 20.0}, "RSI band 70/30 -> 80/20"),
    ({"trigger_length": 10}, "trigger length 5 -> 10"),
    ({"trigger_length": 20}, "trigger length 5 -> 20"),
    ({"wave_length": 55}, "wave length 34 -> 55"),
    ({"fast_wave_length": 13, "slow_wave_length": 34}, "waves 8/21 -> 13/34"),
    ({"atr_stop_multiplier": 2.00}, "ATR stop x1.10 -> x2.00"),
    ({"atr_stop_multiplier": 3.00}, "ATR stop x1.10 -> x3.00"),
]

for config, label in sweeps:
    row = run(config, label)
    rows.append(row)
    print(f"{label:<28} n={row.get('n', 0):>5}  mean_r={row.get('mean_r')}  "
          f"pf={row.get('profit_factor')}  win={row.get('win_rate')}  "
          f"final={row.get('final_r')}  ({row.get('seconds')}s)", flush=True)

with open(r"C:\Project\2026\scratch\backtest_sweep.json", "w", encoding="utf-8") as fh:
    json.dump(rows, fh, indent=2)
print("\nwritten: scratch/backtest_sweep.json")
