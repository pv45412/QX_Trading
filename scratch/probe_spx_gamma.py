"""Scratch: why does $SPX produce zero gamma while SPY does not?"""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.app import context as C  # noqa: E402

for symbol in ("SPY", "$SPX", "$NDX"):
    try:
        frame, spot, meta = C._chain_frame(C.chain_symbol(symbol), max_expiries=2)
    except Exception as exc:  # noqa: BLE001
        print(f"{symbol}: EXC {type(exc).__name__}: {str(exc)[:80]}")
        continue
    print(f"\n=== {symbol} (chain {C.chain_symbol(symbol)}) ===")
    print(f"  spot={spot} contracts={len(frame)} expiries={meta.get('expiries')}")
    if frame.empty:
        print("  EMPTY frame")
        continue
    frame = frame.copy()
    frame["gamma_num"] = frame["gamma"].apply(
        lambda v: float(v) if isinstance(v, (int, float)) else None)
    print(f"  gamma non-null : {frame['gamma_num'].notna().sum()} / {len(frame)}")
    print(f"  open_interest>0: {(frame['open_interest'] > 0).sum()}")
    print(f"  gamma abs sum  : {frame['gamma_num'].abs().sum():.6f}")
    print(f"  sample rows    :")
    for _, row in frame.head(3).iterrows():
        print(f"     strike={row['strike']} type={row['option_type']} "
              f"oi={row['open_interest']} gamma={row['gamma']!r} dte={row['dte']}")
    zero_oi = (frame["open_interest"] == 0).sum()
    print(f"  rows with ZERO open interest: {zero_oi} / {len(frame)}")
