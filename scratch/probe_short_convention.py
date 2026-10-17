"""Scratch: determine Schwab's short-position field conventions from LIVE data.

F17 hinges on whether `marketValue` is a signed liability for shorts. Rather than
guess, read the real account and inspect the raw fields.
"""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.app import trade  # noqa: E402

accounts = trade.list_accounts().get("accounts") or []
print(f"accounts: {len(accounts)}")

found_short = False
for entry in accounts:
    masked = entry.get("masked")
    acct = entry.get("account_number")
    try:
        detail = trade.account_detail(acct)
    except Exception as exc:  # noqa: BLE001
        print(f"  {masked}: detail failed {type(exc).__name__}: {str(exc)[:60]}")
        continue
    positions = (detail or {}).get("positions") or []
    print(f"\n=== {masked} ({entry.get('type')}) — {len(positions)} positions ===")
    for pos in positions:
        instrument = pos.get("instrument") or {}
        long_qty = pos.get("longQuantity") or 0
        short_qty = pos.get("shortQuantity") or 0
        if not short_qty:
            continue
        found_short = True
        print("  SHORT POSITION FOUND")
        print(f"    symbol            : {instrument.get('symbol')}")
        print(f"    assetType         : {instrument.get('assetType')}")
        print(f"    longQuantity      : {pos.get('longQuantity')}")
        print(f"    shortQuantity     : {pos.get('shortQuantity')}")
        print(f"    averagePrice      : {pos.get('averagePrice')}")
        print(f"    marketValue       : {pos.get('marketValue')}")
        print(f"    longOpenProfitLoss: {pos.get('longOpenProfitLoss')}")
        print(f"    shortOpenProfitLoss:{pos.get('shortOpenProfitLoss')}")
        print(f"    openProfitLoss    : {pos.get('openProfitLoss')}")
        print(f"    currentDayProfitLoss: {pos.get('currentDayProfitLoss')}")

if not found_short:
    print("\nNo live short positions exist right now.")
    print("Showing a LONG position for comparison of the same fields:")
    for entry in accounts:
        try:
            detail = trade.account_detail(entry.get("account_number"))
        except Exception:  # noqa: BLE001
            continue
        for pos in ((detail or {}).get("positions") or []):
            if (pos.get("longQuantity") or 0) > 0:
                print(f"    symbol={((pos.get('instrument') or {}).get('symbol'))} "
                      f"long={pos.get('longQuantity')} avg={pos.get('averagePrice')} "
                      f"marketValue={pos.get('marketValue')} "
                      f"longOpenPL={pos.get('longOpenProfitLoss')} "
                      f"openPL={pos.get('openProfitLoss')}")
                break
        else:
            continue
        break

# Also check OPTIONS specifically, since multiplier handling differs.
print("\n=== any OPTION positions (multiplier check) ===")
for entry in accounts:
    try:
        detail = trade.account_detail(entry.get("account_number"))
    except Exception:  # noqa: BLE001
        continue
    for pos in ((detail or {}).get("positions") or []):
        instrument = pos.get("instrument") or {}
        if str(instrument.get("assetType") or "").upper() == "OPTION":
            print(f"    {instrument.get('symbol')} long={pos.get('longQuantity')} "
                  f"short={pos.get('shortQuantity')} avg={pos.get('averagePrice')} "
                  f"marketValue={pos.get('marketValue')} "
                  f"openPL={pos.get('openProfitLoss')}")
