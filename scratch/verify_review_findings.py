"""Verify the reviewer's findings against the CURRENT code.

For each finding: reproduce it, or show it does not reproduce. A "reproduced"
result means the DEFECT is present, not that the code is correct.
"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace as S

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.explorer import membership, service  # noqa: E402
import qx.explorer.master_auto as master_auto  # noqa: E402
import qx.explorer.momo_trend as momo_trend  # noqa: E402
import qx.explorer.ideas as ideas  # noqa: E402

rows = []


def record(fid, title, verdict, detail):
    rows.append({"finding": fid, "title": title, "verdict": verdict, "detail": detail})
    print(f"  {fid}  {verdict:<16} {title}")
    if detail:
        print(f"        {json.dumps(detail)[:200]}")


cfg = service.DEFAULT_CONFIG

# ---------------------------------------------------------------- F02
base = dict(warmup_ok=True, trade_direction=0, trade_atr=2,
            call_trigger_price=105, put_trigger_price=95, wave_high=104, wave_low=96,
            active_stop=None, call_ready=False, put_ready=True,
            bull_build=False, bear_build=True, bull_stack=False, bear_stack=True)
e = service.classify_entry({"price": 96}, S(**base), cfg)
bear_wrong = (e.get("trigger") == 105 and e.get("invalidation", 0) < e.get("trigger", 0)
              and e.get("target", 0) > e.get("trigger", 0))
record("F02", "Bearish watch uses call trigger + long-side stop/target",
       "REPRODUCED" if bear_wrong else "NOT REPRODUCED",
       {"state": e.get("state"), "trigger": e.get("trigger"),
        "invalidation": e.get("invalidation"), "target": e.get("target")})

# ---------------------------------------------------------------- F01
a = {**base, "trade_direction": 1, "active_stop": 97.8, "trade_entry": 100,
     "active_target2": 104.4, "put_ready": False}
e1 = service.classify_entry({"price": 130}, S(**a), cfg)
ext, _ = service._extension_state(e1, 130)
record("F01", "Chased latched signal still promoted to entry readiness",
       "REPRODUCED" if (e1.get("state") == "TRIGGER_CONFIRMED" and ext) else "NOT REPRODUCED",
       {"state": e1.get("state"), "chase_limit": e1.get("chase_limit"),
        "price": 130, "extension_detected": ext})

# ---------------------------------------------------------------- F03
a3 = {**a, "trade_direction": -1, "trade_entry": 100, "active_stop": 102.2,
      "active_target2": 95.6}
e3 = service.classify_entry({"price": 90}, S(**a3), cfg)
ext3, dist3 = service._extension_state(e3, 90)
record("F03", "Short chase limit points upward; downward chase not detected",
       "REPRODUCED" if (e3.get("chase_limit") == 103.0 and not ext3) else "NOT REPRODUCED",
       {"chase_limit": e3.get("chase_limit"), "price": 90,
        "extension_detected": ext3, "second_value": dist3})

# ---------------------------------------------------------------- F11
b = service._breadth(
    [{"momentum": "BULLISH", "trend": "BULLISH", "history_ok": True, "weight": .5},
     {"momentum": None, "trend": None, "history_ok": False, "weight": .5}],
    membership.UNIVERSE_HOLDINGS)
record("F11", "Breadth reports zero missing when half the members lack data",
       "REPRODUCED" if (b["missing_data"] == 0 and b["denominator"] == 1) else "NOT REPRODUCED",
       {k: b[k] for k in ("denominator", "covered", "missing_data", "weight_covered_pct")})

# ---------------------------------------------------------------- F07
bars = [{"open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i,
         "volume": 100} for i in range(200)]
s = master_auto.latest(bars)
record("F07", "Completed-bar mode drops the final supplied bar unconditionally",
       "REPRODUCED" if s.index == 198 else "NOT REPRODUCED",
       {"input_last_index": 199, "output_index": s.index})

# ---------------------------------------------------------------- F12
m = momo_trend.latest(bars)
pullback_populates = bool(service._apply_view(
    [{"trend": m.trend, "momentum": m.momentum}], "pullback"))
record("F12", "Pullback view requires a TOPS state that cannot occur",
       "REPRODUCED" if (m.trend == "BULLISH" and m.momentum == "BULLISH"
                        and not pullback_populates) else "NOT REPRODUCED",
       {"trend": m.trend, "momentum": m.momentum, "pullback_rows": pullback_populates})

# ---------------------------------------------------------------- F09
with tempfile.TemporaryDirectory() as d:
    original = ideas.SNAPSHOT_PATH
    ideas.SNAPSHOT_PATH = str(Path(d) / "snapshot.json")
    ideas._write_snapshot({"generated_at": "2020-01-01T00:00:00+00:00",
                           "candidates": [{"symbol": "XYZ", "direction": "LONG",
                                           "bucket": "ready_now", "sector_symbol": "XLK",
                                           "rs_market": 0}]})
    x = ideas.ideas()
    record("F09", "Stale snapshot still reports IDEAS_AVAILABLE in ready_now",
           "REPRODUCED" if (x["stale"] and x["verdict"] == "IDEAS_AVAILABLE" and x["shown"])
           else "NOT REPRODUCED",
           {"stale": x["stale"], "verdict": x["verdict"], "shown": x["shown"]})
    ideas.SNAPSHOT_PATH = original

# ---------------------------------------------------------------- F14 / F16 / F15
stub = types.ModuleType("qx.reporting.schwab_activity")
stub.SchwabActivityReader = object
sys.modules["qx.reporting.schwab_activity"] = stub
from qx.app import trade  # noqa: E402

trade._quote = lambda symbol: {"last": 100, "source": "schwab", "realtime": False}
trade.account_detail = lambda account: {"balances": {"equity": 100000, "buying_power": 100000},
                                        "positions": []}

x14 = trade.validate_ticket({"symbol": "XYZ", "side": "BUY", "quantity": 1,
                             "order_type": "MARKET"}, account_number="TEST")
record("F14", "Freshness test accepts a non-realtime stub quote",
       "REPRODUCED" if x14["verdict"] == "READY_FOR_CONFIRMATION" else "NOT REPRODUCED",
       {"verdict": x14["verdict"], "quote": x14.get("quote"), "failed": x14.get("failed")})

x16 = trade.validate_ticket({"symbol": "XYZ", "side": "BUY", "quantity": 1,
                             "order_type": "LIMIT", "limit_price": -1}, account_number="TEST")
limit_passed = next(c for c in x16["checks"] if c["name"] == "limit_price")["passed"]
record("F16a", "Negative limit passes the presence check",
       "REPRODUCED" if limit_passed else "NOT REPRODUCED",
       {"limit_price_check_passed": limit_passed, "estimated_cost": x16.get("estimated_cost"),
        "failed": x16.get("failed")})

# Missing equity -> concentration treated as acceptable
trade.account_detail = lambda account: {"balances": {"equity": 0, "buying_power": 100000},
                                        "positions": []}
x16b = trade.validate_ticket({"symbol": "XYZ", "side": "BUY", "quantity": 1,
                              "order_type": "MARKET"}, account_number="TEST")
conc = next(c for c in x16b["checks"] if c["name"] == "concentration")
record("F16b", "Missing equity passes the concentration check",
       "REPRODUCED" if conc["passed"] else "NOT REPRODUCED",
       {"concentration_passed": conc["passed"], "detail": conc["detail"]})
trade.account_detail = lambda account: {"balances": {"equity": 100000, "buying_power": 100000},
                                        "positions": []}

with tempfile.TemporaryDirectory() as d:
    original_store = trade.ORDER_STORE
    trade.ORDER_STORE = str(Path(d) / "orders.json")
    ticket = {"symbol": "XYZ", "side": "BUY", "quantity": 1, "order_type": "MARKET"}
    r1 = trade.submit_simulated(ticket, account_number="TEST", confirm=True)
    r2 = trade.submit_simulated(ticket, account_number="TEST", confirm=True)
    count = trade.list_orders()["count"]
    record("F15", "Repeated identical MARKET submissions create duplicate fills",
           "REPRODUCED" if (r1.get("ok") and r2.get("ok") and count == 2) else "NOT REPRODUCED",
           {"count": count, "statuses": [r1.get("order", {}).get("status"),
                                         r2.get("order", {}).get("status")]})
    trade.ORDER_STORE = original_store

# ---------------------------------------------------------------- F05 / F17
from qx.reporting.pnl_engine import realized_pnl, unrealized_pnl  # noqa: E402


def tx(t, sym, effect, qty, cost):
    return {"type": "TRADE", "time": t, "transferItems": [
        {"instrument": {"assetType": "OPTION", "symbol": sym, "underlyingSymbol": "XYZ"},
         "positionEffect": effect, "amount": qty, "cost": cost}]}


f5 = realized_pnl([tx("2026-01-01", "XYZ CALL A", "OPENING", 1, -100),
                   tx("2026-01-02", "XYZ CALL B", "OPENING", 1, -500),
                   tx("2026-01-03", "XYZ CALL B", "CLOSING", -1, 600)])
record("F05", "Options FIFO matches different contracts as one instrument",
       "REPRODUCED" if f5["realized_gross"] == 500 else "NOT REPRODUCED",
       {"realized_gross": f5["realized_gross"], "correct_match_would_be": 100})

u = unrealized_pnl({"positions": [{"instrument": {"symbol": "XYZ", "assetType": "EQUITY"},
                                   "shortQuantity": 10, "averagePrice": 100,
                                   "marketValue": -900}]})
record("F17a", "Short fallback sign produces a large negative unrealized",
       "REPRODUCED" if u["total_unrealized"] == -1900 else "NOT REPRODUCED",
       {"total_unrealized": u["total_unrealized"],
        "expected_if_signed_liability_convention": 100})

p = realized_pnl([tx("2026-01-01", "XYZ CALL A", "OPENING", 1, -100),
                  tx("2026-01-02", "XYZ CALL A", "CLOSING", -2, 300)])
record("F17b", "Partial close leaves the residual quantity unreported",
       "REPRODUCED" if (p["trades"] and p["trades"][0]["partial"]
                        and not p["unmatched_closes"]) else "NOT REPRODUCED",
       {"partial_flag": bool(p["trades"] and p["trades"][0]["partial"]),
        "unmatched_closes": p["unmatched_closes"]})

# ---------------------------------------------------------------- F08
src = Path(r"C:\Project\2026\src\qx\explorer\service.py").read_text(encoding="utf-8")
applies_timeframe = "interval=timeframe" in src or "minutes=minutes" in src
record("F08", "Explorer accepts a timeframe argument without applying it",
       "REPRODUCED" if not applies_timeframe else "ALREADY FIXED",
       {"applies_interval": "interval=timeframe" in src,
        "passes_minutes": "minutes=" in src})

# ---------------------------------------------------------------- F04
ui = Path(r"C:\Project\2026\src\qx\app\ui.py").read_text(encoding="utf-8")
has_ui_executable = "EXECUTABLE'" in ui or 'EXECUTABLE"' in ui
record("F04", "Discover UI derives an EXECUTABLE label in the browser",
       "REPRODUCED" if has_ui_executable else "ALREADY FIXED",
       {"ui_mentions_executable": has_ui_executable})

Path(r"C:\Project\2026\scratch\review_verify.json").write_text(
    json.dumps(rows, indent=2), encoding="utf-8")
repro = sum(1 for r in rows if r["verdict"] == "REPRODUCED")
print(f"\n{repro} of {len(rows)} checked findings REPRODUCED on the current code")
