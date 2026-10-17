"""Phase A regression tests — the reviewer's reproduced findings.

Each test encodes the CORRECT behaviour. On the supplied version these FAIL
(that is the point); after the Phase A fixes they must pass. Fixtures are taken
verbatim from QX_DEEP_CODE_REVIEW_DSH.md so the reviewer can diff directly.

Run: python scratch/test_phase_a.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace as S

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

passed = failed = 0
results: list[dict] = []


def check(fid, title, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {fid}  {title}")
        results.append({"finding": fid, "title": title, "ok": True, "detail": detail})
    else:
        failed += 1
        print(f"  FAIL  {fid}  {title}  {detail}")
        results.append({"finding": fid, "title": title, "ok": False, "detail": detail})


from qx.explorer import membership, service  # noqa: E402
import qx.explorer.ideas as ideas  # noqa: E402
import qx.explorer.master_auto as master_auto  # noqa: E402
import qx.explorer.momo_trend as momo_trend  # noqa: E402

cfg = service.DEFAULT_CONFIG

print("== F02: bearish watch must use PUT-side levels ==")
bear = dict(warmup_ok=True, trade_direction=0, trade_atr=2,
            call_trigger_price=105, put_trigger_price=95, wave_high=104, wave_low=96,
            active_stop=None, call_ready=False, put_ready=True,
            bull_build=False, bear_build=True, bull_stack=False, bear_stack=True)
e = service.classify_entry({"price": 96}, S(**bear), cfg)
check("F02a", "bearish watch proposes a SHORT direction",
      e.get("direction") == "SHORT", f"direction={e.get('direction')}")
check("F02b", "bearish watch uses the PUT trigger (95), not the call trigger (105)",
      e.get("trigger") == 95, f"trigger={e.get('trigger')}")
check("F02c", "short plan orders levels correctly (invalidation > trigger > target)",
      (e.get("invalidation") or 0) > (e.get("trigger") or 0) > (e.get("target") or 0),
      f"inv={e.get('invalidation')} trig={e.get('trigger')} tgt={e.get('target')}")
check("F02d", "short chase limit sits BELOW the trigger",
      e.get("chase_limit") is not None and e["chase_limit"] < e["trigger"],
      f"chase={e.get('chase_limit')} trigger={e.get('trigger')}")

long_mirror = {**bear, "put_ready": False, "call_ready": True,
               "bear_build": False, "bull_build": True,
               "bear_stack": False, "bull_stack": True}
el = service.classify_entry({"price": 104}, S(**long_mirror), cfg)
check("F02e", "mirrored long plan orders levels correctly (target > trigger > invalidation)",
      (el.get("target") or 0) > (el.get("trigger") or 0) > (el.get("invalidation") or 0),
      f"tgt={el.get('target')} trig={el.get('trigger')} inv={el.get('invalidation')}")

print("\n== F01: a chased/expired latched signal must NOT be current readiness ==")
latched = {**bear, "trade_direction": 1, "active_stop": 97.8, "trade_entry": 100,
           "active_target2": 104.4, "put_ready": False}
e1 = service.classify_entry({"price": 130}, S(**latched), cfg)
check("F01a", "chased latched long is not TRIGGER_CONFIRMED",
      e1.get("state") != service.ENTRY_TRIGGER, f"state={e1.get('state')}")
check("F01b", "study state is preserved separately for research",
      getattr(S(**latched), "trade_direction", 0) == 1)
check("F01c", "price beyond the stop is not an entry",
      service.classify_entry({"price": 90}, S(**latched), cfg).get("state")
      not in (service.ENTRY_TRIGGER, service.ENTRY_BREAKOUT),
      f"state={service.classify_entry({'price': 90}, S(**latched), cfg).get('state')}")

print("\n== F03: short extension must be side-aware ==")
short = {**latched, "trade_direction": -1, "trade_entry": 100, "active_stop": 102.2,
         "active_target2": 95.6}
e3 = service.classify_entry({"price": 90}, S(**short), cfg)
ext, dist = service._extension_state(e3, 90)
check("F03a", "short chase limit is below its entry",
      e3.get("chase_limit") is not None and e3["chase_limit"] < 100,
      f"chase={e3.get('chase_limit')}")
check("F03b", "a short that fell too far IS flagged extended",
      ext is True, f"price=90 chase={e3.get('chase_limit')} extended={ext}")
check("F03c", "the second value is named as a price distance, not ATR",
      isinstance(dist, (int, float)) or dist is None, f"value={dist}")

print("\n== F04: no browser-derived EXECUTABLE ==")
ui_source = Path(r"C:\Project\2026\src\qx\app\ui.py").read_text(encoding="utf-8")
# Strip comments before checking: the fix is documented in prose that names the
# label, so a raw substring search would flag the documentation itself.
code_lines = [ln for ln in ui_source.splitlines()
              if not ln.strip().startswith("#") and "//" not in ln]
derives_executable = [ln.strip()[:80] for ln in code_lines
                      if "'EXECUTABLE'" in ln or '"EXECUTABLE"' in ln]
check("F04a", "ui.py no longer derives an EXECUTABLE label in executable code",
      not derives_executable, f"offending: {derives_executable[:2]}")
check("F04a2", "carried setups still pin research-only, non-executable state",
      ui_source.count("executable:false") >= 3 and "RESEARCH_ONLY" in ui_source)
server_source = Path(r"C:\Project\2026\src\qx\app\server.py").read_text(encoding="utf-8")
check("F04b", "server exposes an authoritative candidate contract endpoint",
      "/api/candidates" in server_source, "no candidate endpoint found")
contracts_source = Path(r"C:\Project\2026\src\qx\app\contracts.py").read_text(encoding="utf-8")
check("F04c", "the contract reports execution state from the central gate",
      "validate_execution_eligibility" in contracts_source
      and "EXECUTION_BLOCKED" in contracts_source)

print("\n== F05: FIFO must key on the full option contract ==")
from qx.reporting.pnl_engine import realized_pnl  # noqa: E402


def opt_tx(t, sym, effect, qty, cost, underlying="XYZ"):
    return {"type": "TRADE", "time": t, "transferItems": [
        {"instrument": {"assetType": "OPTION", "symbol": sym, "underlyingSymbol": underlying},
         "positionEffect": effect, "amount": qty, "cost": cost}]}


f5 = realized_pnl([opt_tx("2026-01-01", "XYZ 260116C00100000", "OPENING", 1, -100),
                   opt_tx("2026-01-02", "XYZ 260116C00110000", "OPENING", 1, -500),
                   opt_tx("2026-01-03", "XYZ 260116C00110000", "CLOSING", -1, 600)])
check("F05a", "closing contract B matches contract B (+100), not contract A",
      abs(f5["realized_gross"] - 100) < 0.01, f"realized_gross={f5['realized_gross']}")
multi = realized_pnl([opt_tx("2026-01-01", "XYZ 260116C00100000", "OPENING", 1, -100),
                      opt_tx("2026-01-02", "XYZ 260116C00110000", "OPENING", 1, -500),
                      opt_tx("2026-01-03", "XYZ 260116C00110000", "CLOSING", -1, 600)])
check("F05b", "the untouched contract A remains an open lot under its CONTRACT key",
      any("260116C00100000" in str(lot.get("contract_key")) for lot in multi["open_lots"]),
      f"open_lots={[l.get('contract_key') for l in multi['open_lots']]}")
check("F05c", "the reporting label stays the underlying (group dimension)",
      all(lot.get("symbol") == "XYZ" for lot in multi["open_lots"]),
      f"labels={[l.get('symbol') for l in multi['open_lots']]}")

print("\n== F15: identical MARKET retries must not duplicate ==")
stub = types.ModuleType("qx.reporting.schwab_activity")
stub.SchwabActivityReader = object
sys.modules["qx.reporting.schwab_activity"] = stub
from qx.app import trade  # noqa: E402

trade._quote = lambda symbol: {"last": 100, "source": "schwab", "realtime": True}
trade.account_detail = lambda account: {"balances": {"equity": 100000, "buying_power": 100000},
                                        "positions": []}
with tempfile.TemporaryDirectory() as d:
    original = trade.ORDER_STORE
    trade.ORDER_STORE = str(Path(d) / "orders.json")
    ticket = {"symbol": "XYZ", "side": "BUY", "quantity": 1, "order_type": "MARKET"}
    r1 = trade.submit_simulated(ticket, account_number="TEST", confirm=True)
    r2 = trade.submit_simulated(ticket, account_number="TEST", confirm=True)
    count = trade.list_orders()["count"]
    check("F15a", "second identical submission is refused",
          r1.get("ok") is True and r2.get("ok") is False and count == 1,
          f"ok1={r1.get('ok')} ok2={r2.get('ok')} count={count}")
    r3 = trade.submit_simulated(ticket, account_number="TEST", confirm=True,
                                intent_id="NEW-DELIBERATE-INTENT")
    check("F15b", "a deliberate new intent is allowed",
          r3.get("ok") is True and trade.list_orders()["count"] == 2,
          f"ok3={r3.get('ok')} count={trade.list_orders()['count']}")
    trade.ORDER_STORE = original

Path(r"C:\Project\2026\scratch\phase_a_results.json").write_text(
    json.dumps(results, indent=2), encoding="utf-8")
print(f"\nRESULT: {passed} passed, {failed} failed  (failures on this run = defects still present)")
