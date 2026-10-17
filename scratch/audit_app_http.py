"""Scratch: end-to-end HTTP verification of the QX workspace app."""
import json

import requests

BASE = "http://127.0.0.1:8790"
ok_count = 0
fail_count = 0


def check(label, condition, extra=""):
    global ok_count, fail_count
    if condition:
        ok_count += 1
        print(f"  PASS  {label} {extra}")
    else:
        fail_count += 1
        print(f"  FAIL  {label} {extra}")


print("== pages ==")
for path, marker in (("/scanner", "Scanner"), ("/trade", "Trade Workspace"), ("/reports", "P&L")):
    r = requests.get(BASE + path, timeout=30)
    check(f"GET {path}", r.status_code == 200 and marker in r.text,
          f"HTTP {r.status_code} len={len(r.text)}")

print("== health ==")
h = requests.get(BASE + "/api/health", timeout=15).json()
check("/api/health", h.get("ok") is True, json.dumps(h))

print("== scanner data ==")
ctx = requests.get(BASE + "/api/context", timeout=60).json()
check("market context", bool(ctx.get("proxies")), f"regime={ctx.get('regime')} freshness={ctx.get('freshness')}")
sec = requests.get(BASE + "/api/sectors", timeout=120).json()
check("sector rankings 11/11", sec.get("ranked") == 11 and sec.get("declared") == 11,
      f"{sec.get('ranked')}/{sec.get('declared')} top={sec['sectors'][0]['symbol']}")

scan = requests.get(BASE + "/api/scan", params={"symbols": "SPY,AAPL,NVDA", "timeframe": "1d"}, timeout=180).json()
check("scan swing", scan.get("symbols") == 3, f"verdict={scan.get('verdict')} actionable={scan.get('actionable')} rule={scan.get('rule_version')}")
first = scan["results"][0]
check("scan row shape", {"score", "signal", "factors", "entry", "source"} <= set(first),
      f"{first['symbol']} score={first['score']} signal={first['signal']} src={first['source']}")

chart = requests.get(BASE + "/api/chart", params={"symbol": "SPY", "timeframe": "1d"}, timeout=60).json()
check("chart", len(chart.get("closes") or []) > 40, f"{len(chart.get('closes') or [])} closes src={chart.get('source')}")

print("== trade workspace ==")
accts = requests.get(BASE + "/api/trade/accounts", timeout=60).json()
check("trade accounts", len(accts.get("accounts") or []) >= 1,
      ", ".join(a["masked"] + "/" + str(a["type"]) for a in accts.get("accounts", [])))
account = accts["accounts"][0]["account_number"]
detail = requests.get(BASE + "/api/trade/account", params={"account": account}, timeout=120).json()
check("account detail", "balances" in detail and "positions" in detail,
      f"equity={detail['balances']['equity']} positions={len(detail['positions'])} open_orders={len(detail['open_orders'])}")

quote = requests.get(BASE + "/api/chart", params={"symbol": "SPY"}, timeout=60).json()
last = quote["closes"][-1]
limit = round(last * 0.98, 2)
ticket = {"account": account, "symbol": "SPY", "side": "BUY", "quantity": 10,
          "order_type": "LIMIT", "limit_price": limit, "duration": "DAY",
          "setup": {"setup_id": "SPY-1d-LONG", "setup_version": 1, "side": "LONG",
                    "entry": last, "invalidation": round(last * 0.96, 2),
                    "publication_state": "RESEARCH_ONLY", "executable": False}}
val = requests.post(BASE + "/api/trade/validate", json=ticket, timeout=180).json()
check("ticket validation", val.get("verdict") in ("READY_FOR_CONFIRMATION", "BLOCKED"),
      f"verdict={val.get('verdict')} failed={val.get('failed')}")
check("repo EX-gate reported", val.get("ex_gate", {}).get("allowed") is False,
      f"gate={val.get('ex_gate')}")

print("== simulated order + duplicate guard ==")
payload = {"ticket": val["proposed_order"], "account": account, "confirm": True, "setup": ticket["setup"]}
r1 = requests.post(BASE + "/api/trade/orders", json=payload, timeout=180).json()
check("simulated submit", r1.get("ok") is True, f"intent={r1.get('order',{}).get('intent_id')} status={r1.get('order',{}).get('status')}")
r2 = requests.post(BASE + "/api/trade/orders", json=payload, timeout=180).json()
check("duplicate blocked (same ticket)", r2.get("ok") is False and "duplicate" in str(r2.get("error", "")),
      f"error={r2.get('error')}")
intent = r1.get("order", {}).get("intent_id")
if intent:
    c = requests.post(BASE + "/api/trade/orders/cancel", json={"intent_id": intent}, timeout=60).json()
    check("cancel simulated order", c.get("ok") is True, f"status={c.get('order',{}).get('status')}")
orders = requests.get(BASE + "/api/trade/orders", timeout=30).json()
check("order book", orders.get("mode") == "SIMULATED" and orders.get("app_level") is True,
      f"{orders.get('count')} orders")

print("== reports contract ==")
ra = requests.get(BASE + "/api/accounts", timeout=60).json()
check("/api/accounts (reports)", len(ra.get("accounts") or []) >= 1, f"{len(ra.get('accounts') or [])} accounts")
rep = requests.get(BASE + "/api/report", params={"account": account, "days": 90}, timeout=300).json()
check("/api/report", rep.get("quality", {}).get("accounting_scope", "").startswith("per-account"),
      f"closed={rep.get('performance',{}).get('closed_trades')} scope={rep.get('quality',{}).get('accounting_scope','')[:34]}")

print(f"\nRESULT: {ok_count} passed, {fail_count} failed")
