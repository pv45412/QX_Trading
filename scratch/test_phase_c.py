"""Phase C regression tests — F16 (typed risk validation) and F17 (accounting residuals).

Correct behaviour only. On the unfixed code these FAIL; they must pass after the fix.
Run: python scratch/test_phase_c.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import types
from pathlib import Path

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

passed = failed = 0
results: list[dict] = []


def check(fid, title, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {fid}  {title}")
    else:
        failed += 1
        print(f"  FAIL  {fid}  {title}  {detail}")
    results.append({"finding": fid, "title": title, "ok": bool(condition), "detail": str(detail)})


# --------------------------------------------------------------------------- #
# F17 — unrealized sign and unmatched partial residuals
# --------------------------------------------------------------------------- #
from qx.reporting.pnl_engine import realized_pnl, unrealized_pnl  # noqa: E402

print("== F17a: short unrealized must use the SIGNED identity ==")

# Reviewer's exact fixture: short 10 @ 100, marketValue -900 => unrealized +100.
short = unrealized_pnl({"positions": [{
    "instrument": {"symbol": "XYZ", "assetType": "EQUITY"},
    "shortQuantity": 10, "averagePrice": 100, "marketValue": -900}]})
row = short["positions"][0]
check("F17a1", "short unrealized is +100 (not -1900)",
      abs(row["unrealized"] - 100.0) < 0.01, f"unrealized={row['unrealized']}")
check("F17a2", "short total_unrealized is +100",
      abs(short["total_unrealized"] - 100.0) < 0.01, f"total={short['total_unrealized']}")
check("F17a3", "cost basis is reported as a positive magnitude",
      abs(row["cost_basis"] - 1000.0) < 0.01, f"cost_basis={row['cost_basis']}")
check("F17a4", "quantity is signed negative for a short",
      row["quantity"] == -10, f"quantity={row['quantity']}")

# A losing short: short 10 @ 100, price rose to 110 => marketValue -1100, unrealized -100
losing = unrealized_pnl({"positions": [{
    "instrument": {"symbol": "XYZ", "assetType": "EQUITY"},
    "shortQuantity": 10, "averagePrice": 100, "marketValue": -1100}]})
check("F17a5", "a losing short reports -100",
      abs(losing["positions"][0]["unrealized"] + 100.0) < 0.01,
      f"unrealized={losing['positions'][0]['unrealized']}")

# Long must be unchanged: 10 @ 100, marketValue +1100 => +100
long_pos = unrealized_pnl({"positions": [{
    "instrument": {"symbol": "ABC", "assetType": "EQUITY"},
    "longQuantity": 10, "averagePrice": 100, "marketValue": 1100}]})
check("F17a6", "long unrealized still +100 (no regression)",
      abs(long_pos["positions"][0]["unrealized"] - 100.0) < 0.01,
      f"unrealized={long_pos['positions'][0]['unrealized']}")

# Supplied P&L always wins when present.
supplied = unrealized_pnl({"positions": [{
    "instrument": {"symbol": "XYZ", "assetType": "EQUITY"},
    "shortQuantity": 10, "averagePrice": 100, "marketValue": -900,
    "shortOpenProfitLoss": 42.0}]})
check("F17a7", "supplied shortOpenProfitLoss takes precedence",
      abs(supplied["positions"][0]["unrealized"] - 42.0) < 0.01,
      f"unrealized={supplied['positions'][0]['unrealized']}")

# Options carry a x100 multiplier on BOTH sides of the identity.
opt = unrealized_pnl({"positions": [{
    "instrument": {"symbol": "XYZ 260116C00100000", "assetType": "OPTION"},
    "longQuantity": 2, "averagePrice": 5.00, "marketValue": 1200.0}]})
check("F17a8", "option long uses the x100 multiplier",
      abs(opt["positions"][0]["unrealized"] - 200.0) < 0.01,
      f"unrealized={opt['positions'][0]['unrealized']} cost={opt['positions'][0]['cost_basis']}")

opt_short = unrealized_pnl({"positions": [{
    "instrument": {"symbol": "XYZ 260116C00100000", "assetType": "OPTION"},
    "shortQuantity": 2, "averagePrice": 5.00, "marketValue": -800.0}]})
check("F17a9", "short option unrealized is +200",
      abs(opt_short["positions"][0]["unrealized"] - 200.0) < 0.01,
      f"unrealized={opt_short['positions'][0]['unrealized']}")

# A missing market value must not fabricate a number.
nodata = unrealized_pnl({"positions": [{
    "instrument": {"symbol": "XYZ", "assetType": "EQUITY"},
    "shortQuantity": 10, "averagePrice": 100}]})
check("F17a10", "missing market value yields None, not a guessed figure",
      nodata["positions"][0]["unrealized"] is None,
      f"unrealized={nodata['positions'][0]['unrealized']}")


print("\n== F17b: a partially matched close must report its residual ==")


def opt_tx(day, symbol, effect, qty, cost):
    return {"type": "TRADE", "time": f"2026-01-{day}", "transferItems": [{
        "instrument": {"assetType": "OPTION", "symbol": symbol, "underlyingSymbol": "XYZ"},
        "positionEffect": effect, "amount": qty, "cost": cost}]}


partial = realized_pnl([
    opt_tx("01", "XYZ 260116C00100000", "OPENING", 1, -100),
    opt_tx("02", "XYZ 260116C00100000", "CLOSING", -2, 300),
])
check("F17b1", "the matched portion is still reported",
      partial["trade_count"] == 1, f"trades={partial['trade_count']}")
check("F17b2", "the excess quantity is recorded in unmatched_closes",
      len(partial["unmatched_closes"]) == 1,
      f"unmatched={partial['unmatched_closes']}")
if partial["unmatched_closes"]:
    residual = partial["unmatched_closes"][0]
    check("F17b3", "the residual quantity is the unmatched excess (1)",
          abs(residual.get("qty", 0) - 1.0) < 0.01, f"qty={residual.get('qty')}")
    check("F17b4", "the residual explains itself",
          "residual" in str(residual.get("note", "")).lower()
          or "unmatched" in str(residual.get("note", "")).lower(),
          str(residual.get("note"))[:70])
else:
    check("F17b3", "the residual quantity is the unmatched excess (1)", False, "no residual")
    check("F17b4", "the residual explains itself", False, "no residual")

check("F17b5", "a fully matched close produces no residual",
      not realized_pnl([opt_tx("01", "XYZ 260116C00100000", "OPENING", 2, -200),
                        opt_tx("02", "XYZ 260116C00100000", "CLOSING", -2, 300)]
                       )["unmatched_closes"])
check("F17b6", "a close with no opening lot is still recorded",
      len(realized_pnl([opt_tx("02", "XYZ 260116C00100000", "CLOSING", -1, 100)]
                       )["unmatched_closes"]) == 1)


# --------------------------------------------------------------------------- #
# F16 — typed numeric and risk validation
# --------------------------------------------------------------------------- #
print("\n== F16: numeric validation ==")

stub = types.ModuleType("qx.reporting.schwab_activity")
stub.SchwabActivityReader = object
sys.modules["qx.reporting.schwab_activity"] = stub
from qx.app import trade  # noqa: E402

trade._quote = lambda s: {"last": 100, "source": "schwab", "realtime": True,
                          "timestamp": "2026-10-11T20:00:00+00:00"}
trade.account_detail = lambda a: {"balances": {"equity": 100000, "buying_power": 100000},
                                  "positions": []}


def verdict(ticket, account="TEST"):
    return trade.validate_ticket(ticket, account_number=account)


def named(result, name):
    return next((c for c in result["checks"] if c["name"] == name), None)


bad_limit = verdict({"symbol": "XYZ", "side": "BUY", "quantity": 1,
                     "order_type": "LIMIT", "limit_price": -1})
lp = named(bad_limit, "limit_price")
check("F16a1", "a negative limit fails the limit_price check",
      lp is not None and lp["passed"] is False, f"passed={lp and lp['passed']}")
check("F16a2", "a negative limit is not READY_FOR_CONFIRMATION",
      bad_limit["verdict"] != "READY_FOR_CONFIRMATION", bad_limit["verdict"])
check("F16a3", "no negative estimated cost is produced",
      bad_limit.get("estimated_cost") is None or bad_limit["estimated_cost"] >= 0,
      f"estimated_cost={bad_limit.get('estimated_cost')}")

zero_limit = verdict({"symbol": "XYZ", "side": "BUY", "quantity": 1,
                      "order_type": "LIMIT", "limit_price": 0})
check("F16a4", "a zero limit is rejected",
      named(zero_limit, "limit_price")["passed"] is False,
      f"passed={named(zero_limit, 'limit_price')['passed']}")

for label, value in (("NaN", float("nan")), ("inf", float("inf")), ("-inf", float("-inf"))):
    r = verdict({"symbol": "XYZ", "side": "BUY", "quantity": 1,
                 "order_type": "LIMIT", "limit_price": value})
    check(f"F16a5-{label}", f"a {label} limit is rejected",
          named(r, "limit_price")["passed"] is False and r["verdict"] != "READY_FOR_CONFIRMATION",
          f"verdict={r['verdict']}")

for label, value in (("NaN", float("nan")), ("inf", float("inf"))):
    r = verdict({"symbol": "XYZ", "side": "BUY", "quantity": value, "order_type": "MARKET"})
    check(f"F16a6-{label}", f"a {label} quantity is rejected",
          named(r, "quantity")["passed"] is False and r["verdict"] != "READY_FOR_CONFIRMATION",
          f"verdict={r['verdict']}")

check("F16a7", "a negative quantity is rejected",
      named(verdict({"symbol": "XYZ", "side": "BUY", "quantity": -5,
                     "order_type": "MARKET"}), "quantity")["passed"] is False)
check("F16a8", "a fractional equity quantity is rejected",
      named(verdict({"symbol": "XYZ", "side": "BUY", "quantity": 1.5,
                     "order_type": "MARKET"}), "quantity")["passed"] is False)

print("\n== F16: risk validation with missing equity ==")
trade.account_detail = lambda a: {"balances": {"equity": 0, "buying_power": 100000},
                                  "positions": []}
no_equity = verdict({"symbol": "XYZ", "side": "BUY", "quantity": 1, "order_type": "MARKET"})
conc = named(no_equity, "concentration")
check("F16b1", "missing equity does NOT pass concentration",
      conc is not None and conc["passed"] is False, f"passed={conc and conc['passed']}")
check("F16b2", "missing equity blocks confirmation",
      no_equity["verdict"] != "READY_FOR_CONFIRMATION", no_equity["verdict"])

trade.account_detail = lambda a: {"balances": {"equity": 100000, "buying_power": 0},
                                  "positions": []}
no_bp = verdict({"symbol": "XYZ", "side": "BUY", "quantity": 1, "order_type": "MARKET"})
check("F16b3", "zero buying power blocks a buy",
      no_bp["verdict"] != "READY_FOR_CONFIRMATION", no_bp["verdict"])

trade.account_detail = lambda a: {"balances": {"equity": 1000, "buying_power": 1000},
                                  "positions": []}
oversized = verdict({"symbol": "XYZ", "side": "BUY", "quantity": 100, "order_type": "MARKET"})
check("F16b4", "an order far exceeding equity is blocked",
      oversized["verdict"] != "READY_FOR_CONFIRMATION", oversized["verdict"])

print("\n== F16: a good ticket still passes (no over-blocking) ==")
trade.account_detail = lambda a: {"balances": {"equity": 100000, "buying_power": 100000},
                                  "positions": []}
good = verdict({"symbol": "XYZ", "side": "BUY", "quantity": 10, "order_type": "LIMIT",
                "limit_price": 99.5})
check("F16c1", "a valid limit ticket is READY_FOR_CONFIRMATION",
      good["verdict"] == "READY_FOR_CONFIRMATION",
      f"verdict={good['verdict']} failed={[c['name'] for c in good['checks'] if not c['passed']]}")
check("F16c2", "its estimated cost is sane",
      good.get("estimated_cost") is not None and 900 < good["estimated_cost"] < 1100,
      f"estimated_cost={good.get('estimated_cost')}")

Path(r"C:\Project\2026\scratch\phase_c_results.json").write_text(
    json.dumps(results, indent=2), encoding="utf-8")
print(f"\nRESULT: {passed} passed, {failed} failed")
