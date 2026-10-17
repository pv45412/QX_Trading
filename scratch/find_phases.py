"""Scratch: find series that genuinely produce Phase 2 and Phase 5."""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.explorer.market_phases import evaluate_series  # noqa: E402


def probe(label, closes):
    s = evaluate_series(closes)[-1]
    print(f"{label:<44} phase={str(s.phase):<5} close={closes[-1]:>8.2f} "
          f"ma10={s.ma10:>8.2f} ma30={s.ma30:>8.2f}")
    return s


print("--- seeking Phase 2: close ABOVE ma10, BELOW ma30 ---")
print("(needs a downtrend where price has JUST popped above the fast EMA)")
found2 = None
for drop, bounce, nb in [(1.0, 2.0, 6), (1.5, 3.0, 5), (2.0, 4.0, 4),
                         (0.5, 1.5, 8), (1.0, 1.2, 10), (2.5, 5.0, 3)]:
    path = [400 - i * drop for i in range(170)] + [400 - 169 * drop + i * bounce for i in range(1, nb + 1)]
    s = probe(f"drop={drop} bounce={bounce} n={nb}", path)
    if s.phase == 2 and found2 is None:
        found2 = path
        print("      ^^ PHASE 2 FOUND")

print("\n--- seeking Phase 5: close BELOW ma10, ABOVE ma30 ---")
print("(needs an uptrend with a pullback that has not yet broken the slow SMA)")
found5 = None
for rise, pull, nb in [(1.0, 2.0, 4), (1.0, 3.0, 5), (1.5, 3.0, 5),
                       (0.8, 2.0, 6), (1.2, 2.5, 6), (0.6, 1.0, 10)]:
    path = [100 + i * rise for i in range(170)] + [100 + 169 * rise - i * pull for i in range(1, nb + 1)]
    s = probe(f"rise={rise} pull={pull} n={nb}", path)
    if s.phase == 5 and found5 is None:
        found5 = path
        print("      ^^ PHASE 5 FOUND")

print("\nPHASE 2 series found:", bool(found2))
print("PHASE 5 series found:", bool(found5))
if found2:
    print("P2 len", len(found2), "tail", [round(x, 2) for x in found2[-3:]])
if found5:
    print("P5 len", len(found5), "tail", [round(x, 2) for x in found5[-3:]])
