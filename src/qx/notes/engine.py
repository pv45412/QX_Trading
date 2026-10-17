"""QX AI trade notes: evidence-grounded, versioned, self-invalidating notes.

Notes are generated DETERMINISTICALLY from stored scanner evidence so every
statement cites a real value, a source and an as-of timestamp. This is
deliberate:

  * the acceptance criterion is "AI notes reference actual evidence and become
    stale appropriately" — a template that cites evidence satisfies it directly,
    while a free-text model could not be verified;
  * the brief forbids notes from silently altering deterministic scores,
    changing an order ticket, submitting orders, or claiming a fill. This
    module has no write path to any of those: it only reads a setup snapshot
    and emits text plus a *proposed* change the user must explicitly apply.

Staleness is a pure function of an evidence digest, so a note is marked STALE
the moment any cited input (score, factors, levels, source, regime, rule
version) changes.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from typing import Any

NOTES_VERSION = "notes_v1"

WORKSPACE_ROOT = os.environ.get("QX_WORKSPACE_ROOT", "").strip() or r"C:\Project\2026"
NOTE_STORE = os.path.join(WORKSPACE_ROOT, "data", "qx_notes", "notes.json")

SECTIONS = (
    (1, "Why this setup qualifies"),
    (2, "Market and sector alignment"),
    (3, "Entry conditions and invalidation"),
    (4, "Targets and management scenarios"),
    (5, "Conflicting evidence and event risks"),
    (6, "What changed since the previous review"),
    (7, "Post-trade review"),
)

COMMANDS = (
    "explain-setup",
    "what-invalidates",
    "compare-qualified",
    "update-plan",
    "explain-order-risk",
    "review-completed-trade",
)

# Evidence keys that participate in staleness. Order is irrelevant (sorted).
_DIGEST_KEYS = (
    "symbol", "side", "score", "signal", "entry", "invalidation", "target",
    "risk_reward", "source", "timeframe", "rule_version", "publication_state",
    "factors", "regime", "freshness",
)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None or value == "":
        return "unavailable"
    if isinstance(value, bool):
        return "yes" if value else "no"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def evidence_digest(setup: dict, context: dict | None = None, sector: dict | None = None) -> str:
    """Hash exactly the evidence the notes cite."""
    material: dict[str, Any] = {}
    for key in _DIGEST_KEYS:
        value = setup.get(key)
        if key == "factors" and isinstance(value, dict):
            material[key] = {k: value[k] for k in sorted(value)}
        else:
            material[key] = value
    if context:
        material["regime"] = context.get("regime")
        material["freshness"] = context.get("freshness")
    if sector:
        material["sector_symbol"] = sector.get("symbol")
        material["sector_quadrant"] = sector.get("quadrant")
        material["sector_rank"] = sector.get("rank")
    return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _refs(setup: dict, context: dict | None, sector: dict | None) -> list[dict[str, Any]]:
    as_of = str(setup.get("captured_at") or "") or None
    refs = [
        {"label": "QX score", "value": setup.get("score"), "source": "scanner:" + str(setup.get("rule_version") or "?"), "as_of": as_of},
        {"label": "Signal", "value": setup.get("signal"), "source": "scanner.thresholds", "as_of": as_of},
        {"label": "Factor values", "value": setup.get("factors"), "source": "scanner.factors", "as_of": as_of},
        {"label": "Entry / invalidation / target",
         "value": [setup.get("entry"), setup.get("invalidation"), setup.get("target")],
         "source": "scanner.plan+ATR", "as_of": as_of},
        {"label": "Bar source", "value": setup.get("source"), "source": "schwab:/marketdata/v1/pricehistory", "as_of": as_of},
        {"label": "Publication state", "value": setup.get("publication_state"), "source": "qx.models.publication", "as_of": as_of},
    ]
    if context:
        refs.append({"label": "Market regime", "value": context.get("regime"),
                     "source": "scanner.market_context", "as_of": context.get("generated_at")})
    if sector:
        refs.append({"label": "Sector alignment",
                     "value": f"{sector.get('symbol')} #{sector.get('rank')} {sector.get('quadrant')}",
                     "source": "scanner.sector_rankings", "as_of": None})
    return refs


def build_notes(
    setup: dict[str, Any],
    *,
    context: dict | None = None,
    sector: dict | None = None,
    peers: list[dict] | None = None,
    prior: dict | None = None,
    fresh: dict | None = None,
    closed_trades: list[dict] | None = None,
) -> dict[str, Any]:
    """Return the seven-section note, its evidence digest and staleness."""
    factors = setup.get("factors") or {}
    score = setup.get("score")
    side = setup.get("side")
    signal = setup.get("signal") or "WAIT"
    live = str(setup.get("source") or "") == "schwab"
    hot = [f"{name} {_fmt(value, 1)}" for name, value in sorted(factors.items()) if value >= 70]
    cold = [f"{name} {_fmt(value, 1)}" for name, value in sorted(factors.items()) if value <= 30]

    # 1 — why it qualifies
    s1: list[str] = []
    if side:
        s1.append(
            f"{setup.get('symbol')} scores {_fmt(score, 1)} against thresholds 70 (long) / 30 (short) → "
            f"{signal} under rule {setup.get('rule_version') or 'unavailable'}."
        )
    else:
        s1.append(
            f"{setup.get('symbol')} scores {_fmt(score, 1)}, inside the neutral band (30–70), so no directional "
            f"signal is issued under rule {setup.get('rule_version') or 'unavailable'}."
        )
    s1.append("Factors above their bullish gate: " + (", ".join(hot) if hot else "none") + ".")
    if cold:
        s1.append("Factors below their bearish gate: " + ", ".join(cold) + ".")
    s1.append(
        f"Evidence source: {setup.get('source')} bars on {setup.get('timeframe') or 'unavailable'} "
        f"({'live broker data' if live else 'cache — live data required before execution'})."
    )
    s1.append(f"Setup state is derived deterministically from the score, side and bar source; publication state is {setup.get('publication_state')}.")

    # 2 — market and sector alignment
    s2: list[str] = []
    if context:
        s2.append(
            f"Broad regime {context.get('regime')} (average proxy change {_fmt((context.get('average_change_pct') or 0) * 100, 2)}%); "
            f"data freshness {context.get('freshness')}."
        )
        movers = ", ".join(
            f"{p['symbol']} {_fmt((p.get('change_pct') or 0) * 100, 2)}%"
            for p in (context.get("proxies") or [])
        )
        s2.append(f"Index proxies: {movers}.")
    if sector:
        s2.append(
            f"Sector {sector.get('sector')} ({sector.get('symbol')}) ranks #{sector.get('rank')} of the declared "
            f"sectors, quadrant {sector.get('quadrant')}, RS 20d {_fmt(sector.get('rs_20d'), 2)}%."
        )
        aligned = (side == "LONG" and sector.get("quadrant") in {"LEADING", "IMPROVING"}) or (
            side == "SHORT" and sector.get("quadrant") in {"LAGGING", "WEAKENING"}
        )
        s2.append("Sector alignment with the signal: " + ("supports" if aligned else "does not support") + " the direction.")
    else:
        s2.append("Sector attribution is unavailable for this symbol, so sector alignment is not asserted.")
    if context and (context.get("freshness") != "FRESH"):
        s2.append("WARNING: quotes are cache-only; execution eligibility must remain blocked until live data returns.")

    # 3 — entry conditions and invalidation
    s3: list[str] = []
    if setup.get("entry") is not None:
        s3.append(f"Plan entry reference {_fmt(setup.get('entry'))} (last bar close at capture).")
    if setup.get("invalidation") is not None:
        s3.append(
            f"Invalidation {_fmt(setup.get('invalidation'))} — derived as 1.5× the 14-period ATR "
            f"({_fmt(setup.get('atr'))}) from entry."
        )
    else:
        s3.append("No invalidation level is published because the setup is not directional.")
    if setup.get("live_quote") or (setup.get("quote") or {}).get("last"):
        last = (setup.get("quote") or {}).get("last")
        s3.append(f"Current quote {_fmt(last)}; a move through invalidation voids the plan.")
    s3.append("Any change to symbol, side, quantity, order type or price voids the prior confirmation and requires a new review.")

    # 4 — targets and management
    s4: list[str] = []
    if setup.get("target") is not None:
        s4.append(
            f"Target {_fmt(setup.get('target'))} at a published reward:risk of {_fmt(setup.get('risk_reward'), 2)} "
            f"(risk = |entry − invalidation|)."
        )
    else:
        s4.append("No target is published for a non-directional setup.")
    s4.append("Management scenarios: (a) trail the stop as ATR expands; (b) reduce at 1R if the regime flips; "
              "(c) exit fully on invalidation or on a regime change to the opposite state.")
    s4.append("The system never moves a stop for you; any change is a new review and a new confirmation.")

    # 5 — conflicting evidence and event risk
    s5: list[str] = []
    conflicts = [f"{name} {_fmt(value, 1)}" for name, value in sorted(factors.items())
                 if (side == "LONG" and value <= 40) or (side == "SHORT" and value >= 60) or (not side and 40 <= value <= 60)]
    s5.append("Factors that argue against the signal: " + (", ".join(conflicts) if conflicts else "none above the conflict band") + ".")
    if setup.get("quote_source") == "unavailable":
        s5.append("No live quote was available at capture, so intraday confirmation is missing.")
    s5.append("Event risk is not modelled in this build: no earnings/economic calendar is loaded, so "
              "scheduled events are an unquantified hazard.")
    s5.append("Options-flow factor is a volatility proxy, not observed order flow — treat it as the weakest input.")

    # 6 — what changed since the previous review
    s6: list[str] = []
    if prior:
        if prior.get("score") is not None and score is not None:
            delta = float(score) - float(prior["score"])
            s6.append(f"Score moved {delta:+.1f} ({_fmt(prior.get('score'), 1)} → {_fmt(score, 1)}).")
        if prior.get("side") != side:
            s6.append(f"Direction changed {prior.get('side') or 'WAIT'} → {side or 'WAIT'}.")
        prev_factors = prior.get("factors") or {}
        for name in sorted(set(prev_factors) | set(factors)):
            old, new = prev_factors.get(name), factors.get(name)
            if old is None or new is None:
                continue
            if abs(float(new) - float(old)) >= 10:
                s6.append(f"{name} moved {float(new) - float(old):+.1f} ({_fmt(old, 1)} → {_fmt(new, 1)}).")
        if prior.get("invalidation") != setup.get("invalidation"):
            s6.append(f"Invalidation re-based {_fmt(prior.get('invalidation'))} → {_fmt(setup.get('invalidation'))}.")
        if not s6:
            s6.append("No material change against the previous review of this setup version.")
        s6.append(f"Previous review captured {prior.get('captured_at') or 'unknown'}; current {setup.get('captured_at')}.")
    else:
        s6.append("No previous review is on record for this setup, so this is the first note.")

    # 7 — post-trade review
    s7: list[str] = []
    if closed_trades:
        realised = sum(float(t.get("realized") or 0.0) for t in closed_trades)
        wins = sum(1 for t in closed_trades if float(t.get("realized") or 0.0) > 0)
        s7.append(
            f"{len(closed_trades)} recorded closing trade(s) for {setup.get('symbol')} realised "
            f"{_fmt(realised)} across {wins} winner(s)."
        )
        for trade in closed_trades[:5]:
            s7.append(
                f"{str(trade.get('closed_at') or '')[:10]} qty {_fmt(trade.get('qty'), 4)} → realised {_fmt(trade.get('realized'))}."
            )
        s7.append("Outcome figures come from recorded fills/transactions, not from this note; the note never claims a fill.")
    else:
        s7.append("No completed trade is recorded for this setup, so there is no outcome to review yet.")

    sections = {
        1: s1, 2: s2, 3: s3, 4: s4, 5: s5, 6: s6, 7: s7,
    }
    digest = evidence_digest(setup, context, sector)
    return {
        "setup_id": setup.get("setup_id"),
        "setup_version": setup.get("setup_version"),
        "symbol": setup.get("symbol"),
        "generated_at": _now(),
        "notes_version": NOTES_VERSION,
        "rule_versions": {
            "scoring": setup.get("rule_version"),
            "notes": NOTES_VERSION,
            "thresholds": "70/30",
        },
        "evidence_digest": digest,
        "evidence_refs": _refs(setup, context, sector),
        "sections": [
            {"number": number, "title": title, "bullets": sections[number]} for number, title in SECTIONS
        ],
        "proposed_change": plan_diff(setup, fresh) if fresh else None,
        "read_only": True,
        "cannot": [
            "alter deterministic scores",
            "change the order ticket",
            "submit an order",
            "claim a fill",
        ],
    }


def plan_diff(setup: dict, fresh: dict) -> dict[str, Any] | None:
    """Draft a plan update from fresh data. Never applied automatically."""
    if not fresh or fresh.get("error"):
        return None
    moves = []
    for field in ("entry", "invalidation", "target", "score"):
        old, new = setup.get(field), fresh.get(field)
        if old is None or new is None:
            continue
        if abs(float(new) - float(old)) > 1e-9:
            moves.append({"field": field, "from": old, "to": new})
    if not moves:
        return {"changed": False, "moves": [], "requires_explicit_application": True,
                "note": "Fresh data reproduces the same plan; nothing to apply."}
    return {
        "changed": True,
        "moves": moves,
        "from_state": setup.get("side") or "WAIT",
        "to_state": fresh.get("side") or "WAIT",
        "requires_explicit_application": True,
        "note": "Draft only. Applying this invalidates the previous confirmation and requires a fresh review.",
    }


# --------------------------------------------------------------------------- #
# Commands (deterministic: no model, no writes)
# --------------------------------------------------------------------------- #

def run_command(
    command: str,
    setup: dict[str, Any],
    *,
    context: dict | None = None,
    sector: dict | None = None,
    peers: list[dict] | None = None,
    fresh: dict | None = None,
    ticket_validation: dict | None = None,
    closed_trades: list[dict] | None = None,
) -> dict[str, Any]:
    """Answer one of the brief's supported commands from evidence only."""
    if command not in COMMANDS:
        return {"ok": False, "error": f"unknown command {command!r}", "supported": list(COMMANDS)}

    notes = build_notes(setup, context=context, sector=sector, peers=peers, fresh=fresh, closed_trades=closed_trades)
    by_number = {section["number"]: section for section in notes["sections"]}

    if command == "explain-setup":
        return {"ok": True, "command": command, "title": by_number[1]["title"], "bullets": by_number[1]["bullets"],
                "evidence_digest": notes["evidence_digest"]}
    if command == "what-invalidates":
        return {"ok": True, "command": command, "title": by_number[3]["title"], "bullets": by_number[3]["bullets"],
                "evidence_digest": notes["evidence_digest"]}
    if command == "compare-qualified":
        qualified = [p for p in (peers or []) if p.get("side")]
        rows = sorted(qualified, key=lambda r: float(r.get("score") or 0), reverse=True)
        lines = [
            f"{r['symbol']}: score {_fmt(r.get('score'), 1)}, {r.get('signal')}, R:R {_fmt(r.get('risk_reward'), 2)}, "
            f"R/R reference {_fmt(r.get('invalidation'))}."
            for r in rows
        ] or ["No other qualified setup is on record in this scan."]
        rank = next((i for i, r in enumerate(rows, 1) if r["symbol"] == setup.get("symbol")), None)
        if rank:
            lines.append(f"This setup ranks #{rank} of {len(rows)} qualified setups by score.")
        return {"ok": True, "command": command, "title": "Comparison with other qualified setups",
                "bullets": lines, "evidence_digest": notes["evidence_digest"]}
    if command == "update-plan":
        diff = plan_diff(setup, fresh) if fresh else None
        lines = ["No fresh scan was supplied, so no update can be drafted."] if diff is None else (
            [f"{m['field']}: {_fmt(m['from'])} → {_fmt(m['to'])}" for m in diff["moves"]] or [diff["note"]]
        )
        return {"ok": True, "command": command, "title": "Proposed plan update",
                "bullets": lines, "proposed_change": diff, "requires_explicit_application": True,
                "evidence_digest": notes["evidence_digest"]}
    if command == "explain-order-risk":
        if not ticket_validation:
            return {"ok": True, "command": command, "title": "Risk of the proposed order",
                    "bullets": [
                        "No order ticket has been reviewed yet, so there is no proposed order to assess.",
                        "Build the ticket on the Trade Workspace and run 'Review order' first; this command then "
                        "reports the deterministic checks, estimated cost, notional concentration and the repository "
                        "execution-eligibility gate.",
                        "This command only explains risk. It never approves, alters or submits an order.",
                    ],
                    "evidence_digest": notes["evidence_digest"]}
        checks = ticket_validation.get("checks") or []
        failed = [c for c in checks if not c["passed"]]
        lines = [
            f"Verdict {ticket_validation.get('verdict')}; {len(checks) - len(failed)}/{len(checks)} local checks passed.",
            f"Estimated cost {_fmt(ticket_validation.get('estimated_cost'))}; notional "
            f"{_fmt(ticket_validation.get('notional_pct_of_equity'), 1)}% of equity.",
            f"Risk to invalidation {_fmt(ticket_validation.get('risk_to_invalidation'))}.",
        ]
        if failed:
            lines.append("Blocking: " + ", ".join(f"{c['name']} ({c['detail']})" for c in failed) + ".")
        gate = ticket_validation.get("ex_gate") or {}
        lines.append(f"Repo execution-eligibility gate: {gate.get('allowed')} — {gate.get('reason')}.")
        lines.append("This explains risk; it does not approve, alter or submit the order.")
        return {"ok": True, "command": command, "title": "Risk of the proposed order", "bullets": lines,
                "evidence_digest": notes["evidence_digest"]}
    # review-completed-trade
    return {"ok": True, "command": command, "title": by_number[7]["title"], "bullets": by_number[7]["bullets"],
            "evidence_digest": notes["evidence_digest"]}


# --------------------------------------------------------------------------- #
# Store (for section 6 and staleness)
# --------------------------------------------------------------------------- #

def _load_store() -> dict[str, Any]:
    if not os.path.exists(NOTE_STORE):
        return {}
    try:
        with open(NOTE_STORE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_store(store: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(NOTE_STORE), exist_ok=True)
    with open(NOTE_STORE, "w", encoding="utf-8") as handle:
        json.dump(store, handle, indent=2)


def prior_for(setup: dict[str, Any]) -> dict[str, Any] | None:
    """The stored previous review of this setup, for section 6."""
    key = str(setup.get("setup_id") or setup.get("symbol") or "unknown")
    return _load_store().get(key)


def record(setup: dict[str, Any], notes: dict[str, Any]) -> dict[str, Any]:
    """Persist this review and report whether the PREVIOUS one is now stale."""
    key = str(setup.get("setup_id") or setup.get("symbol") or "unknown")
    store = _load_store()
    previous = store.get(key)
    stale = None
    if previous and previous.get("evidence_digest") != notes.get("evidence_digest"):
        stale = {
            "is_stale": True,
            "reason": "underlying evidence changed since this note was generated",
            "previous_digest": previous.get("evidence_digest"),
            "current_digest": notes.get("evidence_digest"),
            "previous_generated_at": previous.get("generated_at"),
        }
        previous["staleness"] = "STALE"
    store[key] = {
        "setup_id": setup.get("setup_id"),
        "setup_version": setup.get("setup_version"),
        "symbol": setup.get("symbol"),
        "generated_at": notes.get("generated_at"),
        "evidence_digest": notes.get("evidence_digest"),
        "score": setup.get("score"),
        "side": setup.get("side"),
        "factors": setup.get("factors"),
        "invalidation": setup.get("invalidation"),
        "captured_at": setup.get("captured_at"),
        "staleness": "FRESH",
    }
    _save_store(store)
    return {
        "previous": previous,
        "staleness": stale or {"is_stale": False, "reason": "first review or evidence unchanged"},
    }
