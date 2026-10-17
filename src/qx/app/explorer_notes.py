"""Explorer AI notes: evidence-grounded statements about alignment and entry.

Every statement is generated from the explorer's stored row evidence — no model
call — so each claim cites real values, carries a timestamp, and names the rule
versions behind it. The note cannot alter scores, change a ticket, or submit
anything.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

NOTE_VERSION = "explorer_notes_v1"


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None or value == "":
        return "unavailable"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _pct(value: Any) -> str:
    return "unavailable" if value is None else f"{float(value) * 100:.0f}%"


def build(payload: dict[str, Any]) -> dict[str, Any]:
    """Explain one explored member from its own evidence."""
    row = payload.get("row") or {}
    sector = payload.get("sector") or {}
    breadth = payload.get("breadth") or {}
    parent = payload.get("parent") or {}
    symbol = str(row.get("symbol") or "")

    momentum = row.get("momentum")
    trend = row.get("trend")
    entry = row.get("entry") or {}
    state = entry.get("state")
    rs_parent = (row.get("rs_vs_parent") or {}).get("20d")
    rs_market = (row.get("rs_vs_market") or {}).get("20d")
    aligned = momentum == "BULLISH" and trend == "BULLISH"

    lines: list[str] = []
    missing: list[str] = []

    # 1 — why it is (or is not) aligned
    if momentum is None or trend is None:
        missing.append("momentum/trend")
        lines.append(f"{symbol}: momentum and trend are UNKNOWN — not enough completed history.")
    elif aligned:
        lines.append(
            f"Momentum and trend are UP on completed {sector.get('timeframe') or 'daily'} bars "
            f"(rule {row.get('rule_version')})."
        )
    else:
        lines.append(
            f"{symbol} is not aligned: momentum {momentum}, trend {trend}. "
            "Only momentum UP with trend UP enters the qualified view."
        )
    if row.get("newly_aligned"):
        lines.append(f"Alignment BEGAN on the latest completed bar (bars since: {row.get('bars_since_alignment')}).")
    elif row.get("bars_since_alignment") is not None:
        lines.append(f"Alignment has held {row['bars_since_alignment']} bars.")
    if row.get("phase") is not None:
        lines.append(f"James Boyd phase: {row.get('phase')} — {row.get('phase_label')}.")

    # 2 — leadership
    if rs_parent is None or rs_market is None:
        missing.append("relative strength")
        lines.append("Relative strength is unavailable (insufficient matched history).")
    else:
        leads_parent = rs_parent > 0
        leads_market = rs_market > 0
        lines.append(
            f"Leads its parent ETF by {rs_parent:+.2f}% and the market by {rs_market:+.2f}% over 20 days "
            f"({'above' if leads_parent else 'below'} parent, {'above' if leads_market else 'below'} market)."
        )
        if leads_parent and leads_market:
            lines.append("Relative strength supports leadership — this is a leadership measure, not proof a trade is ready.")
        else:
            lines.append("Relative strength does NOT support leadership; lagging names are weaker candidates.")

    # 3 — sector participation
    if breadth.get("aligned_pct") is None:
        missing.append("breadth")
        lines.append("Sector breadth is unavailable for this universe.")
    else:
        pct = breadth["aligned_pct"]
        lines.append(
            f"Sector participation: {_pct(pct)} of {breadth.get('covered')} covered members are UP/UP "
            f"(denominator {breadth.get('denominator')}, missing {breadth.get('missing_data')})."
        )
        lines.append(
            "Participation is broad." if pct >= 0.5 else
            "Participation is narrow — a few names may be carrying the ETF."
        )
        if breadth.get("holdings_weighted_aligned_pct") is not None:
            lines.append(
                f"Holdings-weighted alignment {_pct(breadth['holdings_weighted_aligned_pct'])} vs equal-weight "
                f"{_pct(pct)} — a large gap means the move is concentrated in big holdings."
            )
        if breadth.get("weight_covered_pct") is not None:
            lines.append(
                f"Universe coverage: rows represent {_fmt(breadth['weight_covered_pct'], 1)}% of fund weight "
                f"({sector.get('universe')})."
            )

    # 4 — entry quality, explicitly separate from alignment
    if state:
        lines.append(f"Entry condition: {state} — {entry.get('reason')}.")
        if entry.get("trigger") is not None:
            lines.append(
                f"Trigger {_fmt(entry.get('trigger'))}, structural invalidation {_fmt(entry.get('invalidation'))}, "
                f"target {_fmt(entry.get('target'))}, net reward/risk {_fmt(entry.get('reward_risk'))}, "
                f"chase limit {_fmt(entry.get('chase_limit'))}."
            )
        if state == "EXTENDED_WAIT" or row.get("extended"):
            lines.append(
                "Entry remains WAIT because price exceeds the playbook's chase limit; "
                "a qualifying pullback or fresh consolidation is required."
            )
        elif state == "TRIGGER_CONFIRMED":
            lines.append("A plan is live under QX MASTER AUTO's own direction latch. This is a STUDY signal, not an executable order.")
    else:
        missing.append("entry classification")
        lines.append("No entry classification is available.")

    # 5 — conflicts
    conflicts: list[str] = []
    if aligned and rs_parent is not None and rs_parent < 0:
        conflicts.append("aligned but lagging its own parent ETF")
    if aligned and breadth.get("aligned_pct") is not None and breadth["aligned_pct"] < 0.4:
        conflicts.append("aligned inside narrow sector participation")
    if row.get("rvol") is not None and row["rvol"] < 1.0:
        conflicts.append(f"relative volume below average ({_fmt(row.get('rvol'))}x)")
    if parent.get("aligned_up") is False:
        conflicts.append("the parent ETF itself is not aligned")
    lines.append("Conflicting evidence: " + ("; ".join(conflicts) + "." if conflicts else "none identified from the stored evidence."))

    # 6 — what must happen next
    if state == "TRIGGER_CONFIRMED":
        nxt = "Manage the live plan; a new entry requires a fresh signal after the current direction clears."
    elif state == "BREAKOUT_WATCH":
        nxt = "Wait for the entry candle through the trigger with volume confirmation."
    elif state == "PULLBACK_CANDIDATE":
        nxt = "Wait for a pullback that holds the structure, then a fresh break of the trigger."
    elif state == "EXTENDED_WAIT":
        nxt = "Wait for price to return inside the chase limit before considering entry."
    elif not aligned:
        nxt = "No action: the stock must first reach momentum UP with trend UP."
    else:
        nxt = "Wait for a valid structure to form."
    lines.append(f"Next required event: {nxt}")

    return {
        "ok": True,
        "note_version": NOTE_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "symbol": symbol,
        "as_of": row.get("as_of"),
        "rule_versions": {
            "momo_trend": row.get("rule_version"),
            "phases": sector.get("rules", {}).get("phases"),
            "entry": sector.get("rules", {}).get("entry"),
            "notes": NOTE_VERSION,
        },
        "evidence": {
            "momentum": momentum, "trend": trend,
            "bars_since_alignment": row.get("bars_since_alignment"),
            "phase": row.get("phase"),
            "rs_vs_parent_20d": rs_parent, "rs_vs_market_20d": rs_market,
            "entry_state": state, "rvol": row.get("rvol"),
            "breadth": {"aligned_pct": breadth.get("aligned_pct"),
                        "covered": breadth.get("covered"),
                        "denominator": breadth.get("denominator")},
        },
        "missing_inputs": missing,
        "statements": lines,
        "cannot": ["alter deterministic scores", "change an order ticket",
                   "submit an order", "claim a fill"],
        "read_only": True,
    }
