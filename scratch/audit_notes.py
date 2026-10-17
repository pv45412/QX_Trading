"""Scratch: verify the AI trade notes engine end-to-end (deterministic, no HTTP)."""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.notes import engine as notes  # noqa: E402
from qx.scanner import market_context, scan_universe, sector_rankings  # noqa: E402


def safe(text):
    return str(text).encode("ascii", "replace").decode("ascii")

scan = scan_universe(["SPY", "QQQ", "AAPL", "MSFT", "NVDA"])
context = market_context()
sectors = sector_rankings()

row = next((r for r in scan["results"] if r.get("side")), scan["results"][0])
setup = {
    **row,
    "setup_id": f"{row['symbol']}-{scan['timeframe']}-{row.get('side') or 'WAIT'}",
    "setup_version": 1,
    "publication_state": "RESEARCH_ONLY",
    "executable": False,
    "captured_at": "2026-10-07T12:00:00+00:00",
}
sector = next((s for s in sectors["sectors"] if s["symbol"] == setup["symbol"]), None)

result = notes.build_notes(setup, context=context, sector=sector, peers=scan["results"])
print(f"NOTE for {setup['symbol']} (score {setup['score']}) digest={result['evidence_digest']} version={result['notes_version']}")
print(f"sections={len(result['sections'])} refs={len(result['evidence_refs'])}")
ok_sections = [s["number"] for s in result["sections"]] == [1, 2, 3, 4, 5, 6, 7]
print("all 7 sections present:", ok_sections)
for section in result["sections"]:
    print(f"\n--- {section['number']}. {section['title']}")
    for bullet in section["bullets"]:
        print("   *", safe(bullet[:190]))

print("\n== commands ==")
ticket_validation = {"verdict": "READY_FOR_CONFIRMATION",
                     "checks": [{"name": "quantity", "passed": True, "detail": "qty=10"},
                                {"name": "data_freshness", "passed": True, "detail": "quote source=schwab"}],
                     "estimated_cost": 7790.90, "notional_pct_of_equity": 26.3,
                     "risk_to_invalidation": 311.6,
                     "ex_gate": {"allowed": False, "reason": "publication_state is 'RESEARCH_ONLY'"}}
fresh = next((r for r in scan["results"] if r["symbol"] == setup["symbol"]), None)
for command in notes.COMMANDS:
    answer = notes.run_command(command, setup, context=context, sector=sector, peers=scan["results"],
                              fresh=fresh, ticket_validation=ticket_validation,
                              closed_trades=[{"symbol": setup["symbol"], "realized": 120.5, "qty": 10, "closed_at": "2026-09-01T15:00:00+00:00"}])
    print(f"  {command:<24} ok={answer.get('ok')} bullets={len(answer.get('bullets') or [])} :: {safe((answer.get('bullets') or [''])[0][:110])}")

print("\n== staleness ==")
first = notes.record(setup, result)
print("  first record  :", first["staleness"])
again = notes.build_notes(setup, context=context, sector=sector)
second = notes.record(setup, again)
print("  unchanged     :", second["staleness"])
changed = {**setup, "score": float(setup["score"]) - 12.0, "factors": {**setup["factors"], "SMC": 40.0}}
changed_notes = notes.build_notes(changed, context=context, sector=sector)
third = notes.record(changed, changed_notes)
print("  evidence moved:", third["staleness"])
print("\ndigests:", result["evidence_digest"], again["evidence_digest"], changed_notes["evidence_digest"])
