"""Scratch: HTTP verification of the AI trade notes endpoints."""
import requests

BASE = "http://127.0.0.1:8790"
ok = fail = 0


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


print("== notes markup present in pages ==")
for path in ("/scanner", "/trade"):
    text = requests.get(BASE + path, timeout=30).text
    check(f"{path} has notes UI", "AI trade notes" in text and "notesHtml" in text)

print("== build a real setup from live data ==")
scan = requests.get(BASE + "/api/scan", params={"symbols": "SPY,QQQ,AAPL", "timeframe": "1d"}, timeout=180).json()
row = next((r for r in scan["results"] if r.get("side")), scan["results"][0])
setup = {**row, "setup_id": f"{row['symbol']}-1d-{row.get('side') or 'WAIT'}", "setup_version": 1,
         "rule_version": scan["rule_version"], "timeframe": scan["timeframe"],
         "publication_state": "RESEARCH_ONLY", "executable": False,
         "captured_at": "2026-10-07T12:00:00+00:00"}
context = requests.get(BASE + "/api/context", timeout=60).json()
sectors = requests.get(BASE + "/api/sectors", timeout=120).json()
sector = next((s for s in sectors["sectors"] if s["symbol"] == setup["symbol"]), None)
print(f"   setup {setup['symbol']} score={setup['score']} rule={setup['rule_version']}")

print("== POST /api/notes ==")
payload = {"setup": setup, "context": context, "sector": sector, "peers": scan["results"]}
notes = requests.post(BASE + "/api/notes", json=payload, timeout=180).json()
check("/api/notes ok", notes.get("ok") is True)
n = notes.get("notes") or {}
check("7 sections", [s["number"] for s in n.get("sections", [])] == [1, 2, 3, 4, 5, 6, 7],
      f"{len(n.get('sections') or [])} sections")
check("evidence refs cited", len(n.get("evidence_refs") or []) >= 6, f"{len(n.get('evidence_refs') or [])} refs")
check("rule version cited", n.get("rule_versions", {}).get("scoring") == scan["rule_version"],
      f"scoring={n.get('rule_versions',{}).get('scoring')}")
check("no 'None' leakage", "None" not in " ".join(b for s in n.get("sections", []) for b in s["bullets"]))
check("reports its own limits", bool(n.get("cannot")), ", ".join(n.get("cannot") or []))
check("staleness reported", "staleness" in notes, str((notes.get("staleness") or {}).get("staleness", {}).get("is_stale")))

print("== repeat build marks previous stale when evidence moves ==")
notes2 = requests.post(BASE + "/api/notes", json=payload, timeout=180).json()
check("unchanged stays fresh",
      (notes2.get("staleness") or {}).get("staleness", {}).get("is_stale") is False)
moved = {**setup, "score": float(setup["score"]) - 15.0, "factors": {**setup["factors"], "SMC": 25.0}}
notes3 = requests.post(BASE + "/api/notes", json={"setup": moved, "context": context, "sector": sector}, timeout=180).json()
check("moved evidence flags stale",
      (notes3.get("staleness") or {}).get("staleness", {}).get("is_stale") is True,
      f"digests {notes3.get('staleness',{}).get('staleness',{}).get('previous_digest')} -> "
      f"{notes3.get('staleness',{}).get('staleness',{}).get('current_digest')}")
check("section 6 records the change",
      any("Score moved" in b for b in (notes3["notes"]["sections"][5]["bullets"])),
      " ".join(notes3["notes"]["sections"][5]["bullets"])[:110])

print("== POST /api/notes/command (all six) ==")
ticket_validation = {"verdict": "READY_FOR_CONFIRMATION",
                     "checks": [{"name": "quantity", "passed": True, "detail": "qty=10"}],
                     "estimated_cost": 7790.0, "notional_pct_of_equity": 26.0, "risk_to_invalidation": 300.0,
                     "ex_gate": {"allowed": False, "reason": "publication_state is 'RESEARCH_ONLY'"}}
for command in ("explain-setup", "what-invalidates", "compare-qualified", "update-plan",
                "explain-order-risk", "review-completed-trade"):
    body = {"command": command, "setup": setup, "context": context, "sector": sector,
            "peers": scan["results"], "ticket_validation": ticket_validation}
    answer = requests.post(BASE + "/api/notes/command", json=body, timeout=180).json()
    check(f"command {command}", answer.get("ok") is True and answer.get("bullets"),
          f"{len(answer.get('bullets') or [])} bullets :: {(answer.get('bullets') or [''])[0][:80]}")

print(f"\nRESULT: {ok} passed, {fail} failed")
