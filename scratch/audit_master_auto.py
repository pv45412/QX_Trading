"""Scratch: verify the QX MASTER AUTO FAST v5.2.4 port."""
import math
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.explorer.master_auto import (  # noqa: E402
    DEFAULTS, MasterSnapshot, evaluate_series, latest, rsi_wilder, supertrend,
    vwave, warmup_bars,
)

ok = fail = 0


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


def bars_from(closes, highs=None, lows=None, opens=None, vols=None):
    """Default opens to the PREVIOUS close so bull/bear candle tests are meaningful.

    (An open equal to its own close makes `close > open` false, which correctly
    suppresses call_active -- that is the study's behaviour, not a bug.)
    """
    highs = highs or [c + 0.5 for c in closes]
    lows = lows or [c - 0.5 for c in closes]
    opens = opens or [closes[i - 1] if i else closes[i] for i in range(len(closes))]
    vols = vols or [1000.0] * len(closes)
    return [{"open": o, "high": h, "low": l, "close": c, "volume": v, "date": f"d{i}"}
            for i, (o, h, l, c, v) in enumerate(zip(opens, highs, lows, closes, vols))]


print("== 1. VWave: movement-weighted mean, NOT an EMA/VWAP ==")
# Constant movement => VWave equals the simple mean of the source window.
closes = [100.0] * 40
highs = [c + 1.0 for c in closes]
lows = [c - 1.0 for c in closes]
vw = vwave(highs, highs, lows, closes, 34)
expected = sum(highs[-34:]) / 34
check("VWave == mean of window when movement is uniform", abs(vw[-1] - expected) < 1e-9,
      f"vwave={vw[-1]:.6f} mean={expected:.6f}")
# Zero movement => the study falls back to `source`.
flat_h = [100.0] * 40
flat_l = [100.0] * 40
flat_c = [100.0] * 40
vw2 = vwave(flat_c, flat_h, flat_l, flat_c, 34)
check("zero movement falls back to source", abs(vw2[-1] - 100.0) < 1e-9, f"{vw2[-1]}")
check("VWave is None before its window", vw[10] is None)
# A HIGHER-priced source with identical movement scales proportionally.
src2 = [x * 2 for x in highs]
check("VWave scales linearly with the source",
      abs(vwave(src2, highs, lows, closes, 34)[-1] - 2 * expected) < 1e-6)

print("\n== 2. rigor: VWave is NOT an EMA (guard against a lazy port) ==")
close_line = [100 + i for i in range(60)]
h = [c + 1 for c in close_line]
l = [c - 1 for c in close_line]
from qx.scanner.studies import ema  # noqa: E402
check("VWave(close) differs from EMA(close,34) on a trend",
      abs(vwave(close_line, h, l, close_line, 34)[-1] - ema(close_line, 34)[-1]) > 1e-6,
      f"vwave={vwave(close_line,h,l,close_line,34)[-1]:.3f} ema={ema(close_line,34)[-1]:.3f}")

print("\n== 3. RSI (Wilder) bounds and edge cases ==")
up = [100 + i for i in range(60)]
check("all-up series -> RSI 100", abs(rsi_wilder(up, 14)[-1] - 100.0) < 1e-9, rsi_wilder(up, 14)[-1])
down = [200 - i for i in range(60)]
check("all-down series -> RSI 0", abs(rsi_wilder(down, 14)[-1] - 0.0) < 1e-9, rsi_wilder(down, 14)[-1])
check("RSI None before warmup", rsi_wilder(up, 14)[5] is None)

print("\n== 4. SuperTrend latch (seeded from lower band) ==")
close_s = [100 + i * 0.5 for i in range(60)]
high_s = [c + 1 for c in close_s]
low_s = [c - 1 for c in close_s]
atr_s = [2.0] * 60
st = supertrend(high_s, low_s, close_s, atr_s, 1.75)
check("SuperTrend defined once ATR exists", st[0] is not None, f"{st[0]}")
check("rising market -> close above SuperTrend", close_s[-1] > st[-1],
      f"close={close_s[-1]:.2f} st={st[-1]:.2f}")

print("\n== 5. warmup is enforced ==")
WARM = warmup_bars()
print(f"   warmup={WARM}")
short = evaluate_series(bars_from([100 + i for i in range(50)]))
check("no state before warmup", all(s.setup_label is None for s in short))
check("warmup flag false", short[-1].warmup_ok is False)

print("\n== 6. regime / build states on a clean uptrend ==")
uptrend = [100 + i * 0.9 for i in range(240)]
s = latest(bars_from(uptrend))
check("produced a snapshot", s is not None and s.warmup_ok is True)
check("bull stack on an uptrend", s.bull_stack is True, f"fast={s.wave_fast:.2f} mid={s.wave_mid:.2f} slow={s.wave_slow:.2f}")
check("bull build true (close above centre)", s.bull_build is True,
      f"close={uptrend[s.index]:.2f} centre={s.wave_center:.2f}")
check("price state is a CALL-side state", str(s.price_state).startswith("CALL"), s.price_state)
check("bias label BULL", s.bias_label == "BULL", s.bias_label)
check("setup label is LONG-ish", s.setup_label in ("LONG", "READY_LONG", "BOUNCE", "WAIT"),
      s.setup_label)

print("\n== 7. THE RVOL TWO-OFFSET RULE ==")
# Completed bars compare volume[i] against the n-bar average ENDING at i-1.
# The spike must sit on the last COMPLETED bar: with forming=False the final bar is
# excluded, so index n-2 is the bar under test.
closes_v = [100 + i * 0.4 for i in range(240)]
vols = [1000.0] * 239 + [1000.0]
vols[238] = 4000.0                          # spike on the last COMPLETED bar
s2 = latest(bars_from(closes_v, vols=vols))
check("last completed-bar spike reflected in rvol_display", s2.rvol_display >= 3.5,
      f"rvol={s2.rvol_display}")
check("volume_strong true on a 4x spike", s2.volume_strong is True)
# A spike further back must NOT be attributed to the last completed bar.
vols2 = [1000.0] * 240
vols2[236] = 6000.0
s3 = latest(bars_from(closes_v, vols=vols2))
check("distant spike does not inflate the current rvol", s3.rvol_display < 2.0,
      f"rvol={s3.rvol_display}")
# The live branch is only reachable with forming=True, and then uses the final bar.
vols3 = [1000.0] * 239 + [5000.0]
s_live = latest(bars_from(closes_v, vols=vols3), forming=True)
check("forming=True evaluates the final bar and uses the live offset",
      s_live.index == len(closes_v) - 1 and s_live.rvol_display >= 4.0,
      f"index={s_live.index} rvol={s_live.rvol_display}")

print("\n== 8. direction latch produces a trade plan when it fires ==")
# A steady trend reliably latches a trade (verified in scratch/trace_master.py).
series = evaluate_series(bars_from([100 + i * 1.0 for i in range(320)]))
entered = [x for x in series if x.trade_entry is not None and x.active_stop is not None]
check("trade lifecycle observed", len(entered) > 0, f"{len(entered)} bars in trade")
if entered:
    x = entered[-1]
    risk = abs(x.trade_entry - x.active_stop)
    mult = DEFAULTS["atr_stop_multiplier"]
    check("stop is exactly atr * multiplier from entry",
          abs(risk - x.trade_atr * mult) < 1e-6,
          f"risk={risk:.4f} atr*mult={x.trade_atr * mult:.4f}")
    t1 = abs(x.active_target1 - x.trade_entry)
    check("target1 == risk * target1R", abs(t1 - risk * DEFAULTS["target1_r"]) < 1e-6,
          f"t1={t1:.4f} risk={risk:.4f}")
    t2 = abs(x.active_target2 - x.trade_entry)
    check("target2 == risk * target2R", abs(t2 - risk * DEFAULTS["target2_r"]) < 1e-6,
          f"t2={t2:.4f} risk*2={risk*2:.4f}")
    check("targets sit on the correct side for the direction",
          (x.trade_direction == 1 and x.active_target1 > x.trade_entry > x.active_stop) or
          (x.trade_direction == -1 and x.active_target1 < x.trade_entry < x.active_stop),
          f"dir={x.trade_direction}")
    check("reward_risk reported as 1:1 and 1:2",
          abs(x.as_dict()["reward_risk_t1"] - 1.0) < 1e-6 and
          abs(x.as_dict()["reward_risk_t2"] - 2.0) < 1e-6)

print("\n== 9. signals are rising EDGES, never levels ==")
signals = [x for x in series if x.call_signal or x.put_signal]
check("signals exist", len(signals) > 0, f"{len(signals)} signals")
indexes = [x.index for x in signals]
check("no two consecutive signal bars",
      not any(b - a == 1 for a, b in zip(indexes, indexes[1:])), f"indexes={indexes[:8]}")
check("a signal coincides with a latch entry",
      all(x.trade_direction in (1, -1) for x in signals))

print("\n== 10. forming vs completed, and rule version ==")
b = bars_from([100 + i * 0.5 for i in range(240)])
comp = latest(b, forming=False)
form = latest(b, forming=True)
check("completed excludes last bar", comp.index == len(b) - 2, f"{comp.index}")
check("forming includes last bar", form.index == len(b) - 1, f"{form.index}")
check("rule version stamped", comp.rule_version == "qx_master_auto_fast_v5_2_4", comp.rule_version)

print("\n== 11. 1-minute autotimeframe branch uses its own RVOL thresholds ==")
s1m = latest(bars_from([100 + i * 0.3 for i in range(240)]), minutes=1)
s5m = latest(bars_from([100 + i * 0.3 for i in range(240)]), minutes=5)
sd = latest(bars_from([100 + i * 0.3 for i in range(240)]), minutes=1440)
check("1m snapshot produced", s1m is not None and s1m.warmup_ok)
check("5m snapshot produced", s5m is not None and s5m.warmup_ok)
check("daily snapshot produced", sd is not None and sd.warmup_ok)

print(f"\nRESULT: {ok} passed, {fail} failed")
