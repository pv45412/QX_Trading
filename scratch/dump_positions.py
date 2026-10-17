"""Scratch: dump raw position fields to establish Schwab conventions."""
import json
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.app import trade  # noqa: E402

accounts = trade.list_accounts().get("accounts") or []
for entry in accounts:
    acct = entry.get("account_number")
    try:
        detail = trade.account_detail(acct)
    except Exception as exc:  # noqa: BLE001
        print(f"{entry.get('masked')}: {type(exc).__name__}: {str(exc)[:70]}")
        continue
    positions = (detail or {}).get("positions") or []
    print(f"\n===== {entry.get('masked')} ({entry.get('type')}) — {len(positions)} positions =====")
    for pos in positions:
        instrument = pos.get("instrument") or {}
        print(json.dumps({
            "symbol": instrument.get("symbol"),
            "assetType": instrument.get("assetType"),
            "longQuantity": pos.get("longQuantity"),
            "shortQuantity": pos.get("shortQuantity"),
            "averagePrice": pos.get("averagePrice"),
            "marketValue": pos.get("marketValue"),
            "longOpenProfitLoss": pos.get("longOpenProfitLoss"),
            "shortOpenProfitLoss": pos.get("shortOpenProfitLoss"),
            "openProfitLoss": pos.get("openProfitLoss"),
            "currentDayProfitLoss": pos.get("currentDayProfitLoss"),
        }, default=str))
