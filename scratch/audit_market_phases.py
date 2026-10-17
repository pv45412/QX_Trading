"""Scratch: verify the James Boyd 5 Market Phases port."""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.explorer.market_phases import (  # noqa: E402
    PHASE_1, PHASE_2, PHASE_3, PHASE_4, PHASE_5, evaluate_series, hull, latest,
    sma, transition_track, warmup_bars,
)


def hma_reference(values, period):
    """Independent textbook HMA, used to cross-check the ported implementation."""
    import math as _m

    from qx.explorer.market_phases import _wma

    half, root = period // 2, int(_m.sqrt(period))
    w_half, w_full = _wma(values, half), _wma(values, period)
    raw = [None if (a is None or b is None) else 2 * a - b for a, b in zip(w_half, w_full)]
    first = next((i for i, v in enumerate(raw) if v is not None), None)
    if first is None:
        return None
    smoothed = _wma([float(v) for v in raw[first:]], root)
    for value in reversed(smoothed):
        if value is not None:
            return value
    return None

ok = fail = 0


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


def snap(closes, forming=False):
    return latest([{"close": c, "date": f"d{i}"} for i, c in enumerate(closes)], forming=forming)


WARM = warmup_bars()
print(f"warmup={WARM}")

print("\n== 0. Hull MA correctness ==")
# HMA is NOT equal to the line on a rising series: 2*WMA(n/2) - WMA(n) overshoots and
# the final WMA(sqrt(n)) smooths it. The correct invariants are:
#   * exact on a CONSTANT series,
#   * matches an independent reference implementation,
#   * positive and finite where windows are full.
flat_line = [100.0] * 60
check("HMA exact on a constant series", abs(hull(flat_line, 10)[-1] - 100.0) < 1e-9,
      f"hma={hull(flat_line, 10)[-1]}")
line = [100.0 + i for i in range(60)]
ref = hma_reference(line, 10)
check("HMA matches the independent reference", abs(hull(line, 10)[-1] - ref) < 1e-9,
      f"ported={hull(line, 10)[-1]:.6f} ref={ref:.6f}")
check("HMA is None before its window fills", hull(line, 10)[0] is None and hull(line, 10)[5] is None)
s = sma(line, 30)
check("SMA(30) correct", abs(s[-1] - (line[-30] + line[-1]) / 2) < 1e-9, f"{s[-1]:.2f}")

print("\n== 1. short series -> phase None with INSUFFICIENT_WARMUP ==")
short = evaluate_series([100.0] * 20)
check("no phase before warmup", all(x.phase is None for x in short))
check("reason recorded", short[-1].indeterminate_reason == "INSUFFICIENT_WARMUP")

print("\n== 2. monotonic uptrend -> Phase 3 ==")
up = snap([100 + i * 0.8 for i in range(200)])
check("phase is 3", up.phase == PHASE_3, f"phase={up.phase} ma10={up.ma10:.2f} ma30={up.ma30:.2f}")
check("MA10 > MA30 (phase3_ma_crossed true)", up.phase3_ma_crossed is True)
check("not a warning phase", up.warning is False)

print("\n== 3. monotonic downtrend -> Phase 1 ==")
down = snap([300 - i * 0.8 for i in range(200)])
check("phase is 1", down.phase == PHASE_1, f"phase={down.phase}")

print("\n== 4. SUBTLETY: Phase 4 must beat Phase 3 (tested first) ==")
# Uptrend, then flatten so Hull turns down while close stays above both MAs.
phase4_path = [100 + i * 1.2 for i in range(180)] + [316.0 - i * 0.15 for i in range(12)]
p4 = snap(phase4_path)
print(f"   phase={p4.phase} ma10={p4.ma10:.2f} ma30={p4.ma30:.2f} hull_falling={p4.hull_falling} "
      f"ma10>ma30={p4.ma10_gt_ma30}")
check("classified as Phase 4, not Phase 3", p4.phase == PHASE_4, f"phase={p4.phase}")
check("phase 4 is a warning", p4.warning is True)
check("phase 4 subsumes phase-3 structure", p4.phase3_ma_crossed is None,
      "cross flag only reported for an actual Phase 3")

print("\n== 5. SUBTLETY: strict inequality gap -> INDETERMINATE, not a guessed phase ==")
# Construct close exactly equal to MA10: use a long flat run so SMA30 == close,
# then a tiny crafted move so close == EMA10 is unlikely; instead assert the
# INDETERMINATE branch directly via a constant series (close == MA10 == MA30).
flat = snap([100.0] * 200)
print(f"   flat series -> phase={flat.phase} reason={flat.indeterminate_reason}")
check("flat series is indeterminate (close == MA10 == MA30)",
      flat.phase is None and flat.indeterminate_reason == "INDETERMINATE",
      f"phase={flat.phase} reason={flat.indeterminate_reason}")
check("label renders blank like the study", flat.label == " ")

print("\n== 6. Phases 2 and 5 (series located empirically via find_phases.py) ==")
# Phase 2: a downtrend that has JUST popped above the fast EMA but is still under
# the slow SMA -- the first step out of Phase 1.
p2_path = [400 - i * 1.0 for i in range(170)] + [231.0 + i * 2.0 for i in range(1, 7)]
p2 = snap(p2_path)
print(f"   phase2 case -> phase={p2.phase} close={p2_path[-1]:.2f} ma10={p2.ma10:.2f} ma30={p2.ma30:.2f}")
check("Phase 2 detected (above 10EMA, below 30SMA)", p2.phase == PHASE_2, f"phase={p2.phase}")
# NOTE: compare the COMPLETED bar the snapshot describes, not path[-1]. The final
# bar is still forming and is deliberately excluded from published states.
p2_close = p2_path[p2.index]
check("Phase 2 completed close sits between the averages (above fast, below slow)",
      p2.ma30 > p2_close > p2.ma10,
      f"ma10 {p2.ma10:.2f} < close[{p2.index}] {p2_close:.2f} < ma30 {p2.ma30:.2f}")

# Phase 5: an uptrend with a shallow pullback that has not broken the slow SMA.
p5_path = [100 + i * 1.0 for i in range(170)] + [269.0 - i * 2.0 for i in range(1, 5)]
p5 = snap(p5_path)
print(f"   phase5 case -> phase={p5.phase} close={p5_path[-1]:.2f} ma10={p5.ma10:.2f} ma30={p5.ma30:.2f}")
check("Phase 5 detected (below 10EMA, above 30SMA)", p5.phase == PHASE_5, f"phase={p5.phase}")
check("Phase 5 is still a bullish context", p5.bullish is True)
p5_close = p5_path[p5.index]
check("Phase 5 completed close sits between the averages (below fast, above slow)",
      p5.ma10 > p5_close > p5.ma30,
      f"ma10 {p5.ma10:.2f} > close[{p5.index}] {p5_close:.2f} > ma30 {p5.ma30:.2f}")

print("\n== 7. every phase lands in exactly one bucket (mutual exclusivity) ==")
seen = set()
for name, path in (("up", [100 + i * 0.8 for i in range(200)]),
                   ("down", [300 - i * 0.8 for i in range(200)]),
                   ("p4", phase4_path), ("p2", p2_path), ("p5", p5_path)):
    x = snap(path)
    seen.add(x.phase)
    check(f"{name} produced a definite phase", x.phase in (1, 2, 3, 4, 5), f"phase={x.phase}")
check("all five phases are reachable", seen >= {1, 2, 3, 4, 5}, f"observed={sorted(seen)}")

print("\n== 8. forming vs completed ==")
c = [100 + i * 0.8 for i in range(200)]
comp = snap(c, forming=False)
form = snap(c, forming=True)
check("completed excludes final bar", comp.index == len(c) - 2, f"{comp.index}")
check("forming includes final bar", form.index == len(c) - 1, f"{form.index}")

print("\n== 9. transition tracking ==")
series = evaluate_series([100 + i * 0.8 for i in range(200)])
track = transition_track(series)
check("bars_in_phase counted", track["bars_in_phase"] > 1, f"{track['bars_in_phase']}")
check("no spurious warning transition", track["entered_warning"] is False)
check("rule version stamped", series[-1].rule_version == "james_boyd_5_phases_v1")

print(f"\nRESULT: {ok} passed, {fail} failed")
