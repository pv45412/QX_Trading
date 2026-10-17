"""Authoritative candidate contract (reviewer F04, F24).

One server-owned shape that Discover, Explorer, Ideas, Notes and the Trade
Workspace all consume, so no page invents its own decision label. In particular
the browser never derives `EXECUTABLE`: execution eligibility is reported from the
repository's own gate and is always `BLOCKED` while the publication state is not
VERIFIED.

Vocabulary is explicit and non-overlapping:
  research_state      what the scanner/study thinks (directional, not an order)
  study_state         the ported study's own latched opinion (research parity)
  entry_state         current entry readiness, side-aware
  eligibility         ENTRY_ELIGIBLE / ENTRY_EXPIRED / ENTRY_INVALIDATED / None
  execution_state     ALWAYS derived from the central gate — never from a score
"""
from __future__ import annotations

import datetime as dt
from typing import Any

CONTRACT_VERSION = "candidate_contract_v1"

EXECUTION_BLOCKED = "BLOCKED_RESEARCH_ONLY"
EXECUTION_ELIGIBLE = "ELIGIBLE"


def execution_state(setup: dict[str, Any] | None = None,
                    publication_state: str | None = None,
                    executable: bool | None = None) -> dict[str, Any]:
    """Report the repository's execution gate. Never infers eligibility."""
    setup = setup or {}
    pub = publication_state if publication_state is not None else setup.get("publication_state")
    flag = executable if executable is not None else setup.get("executable")
    try:
        from qx.execution.order_router import OrderRouter

        allowed, reason = OrderRouter().validate_execution_eligibility(
            {"publication_state": pub, "executable": flag})
        return {
            "state": EXECUTION_ELIGIBLE if allowed else EXECUTION_BLOCKED,
            "allowed": bool(allowed),
            "reason": reason or "VERIFIED and executable",
            "publication_state": pub,
            "source": "qx.execution.order_router.validate_execution_eligibility",
        }
    except Exception as exc:  # noqa: BLE001 - the gate must fail closed
        return {"state": EXECUTION_BLOCKED, "allowed": False,
                "reason": f"gate unavailable: {type(exc).__name__}", "publication_state": pub,
                "source": "qx.execution.order_router.validate_execution_eligibility"}


def research_state(row: dict[str, Any]) -> str:
    """Directional research label. NEVER an execution label."""
    if row.get("error") or row.get("score") is None:
        return "UNKNOWN"
    if row.get("side"):
        return "QUALIFIED_RESEARCH"
    score = row.get("score")
    if score is not None and (abs(score - 70) <= 5 or abs(score - 30) <= 5):
        return "NEAR_THRESHOLD"
    return "WATCH"


def from_scan_row(row: dict[str, Any], *, rule_version: str | None = None) -> dict[str, Any]:
    """Build the contract from a scanner row."""
    row = dict(row)
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "symbol": row.get("symbol"),
        "company": row.get("company"),
        "sector_symbol": row.get("sector_symbol") or row.get("sector_parent"),
        "direction": row.get("direction") or ("LONG" if row.get("side") == "LONG" else
                                              "SHORT" if row.get("side") == "SHORT" else None),
        "horizon": row.get("horizon") or "SWING",
        "research_state": research_state(row),
        "study_state": row.get("study_state"),
        "entry_state": (row.get("entry") or {}).get("state"),
        "eligibility": (row.get("entry") or {}).get("eligibility"),
        "playbook": (row.get("entry") or {}).get("playbook"),
        "trigger": (row.get("entry") or {}).get("trigger"),
        "invalidation": (row.get("entry") or {}).get("invalidation"),
        "target": (row.get("entry") or {}).get("target"),
        "reward_risk": (row.get("entry") or {}).get("reward_risk"),
        "chase_limit": (row.get("entry") or {}).get("chase_limit"),
        "instrument_evaluation": row.get("instrument_evaluation") or "UNDERLYING_ONLY",
        "execution": execution_state(publication_state="RESEARCH_ONLY", executable=False),
        "rule_version": rule_version or row.get("rule_version"),
        "evidence": {
            "score": row.get("score"), "momentum": row.get("momentum"),
            "trend": row.get("trend"), "phase": row.get("phase"),
            "rs_vs_parent_20d": (row.get("rs_vs_parent") or {}).get("20d")
            if isinstance(row.get("rs_vs_parent"), dict) else row.get("rs_vs_parent"),
            "rs_vs_market_20d": (row.get("rs_vs_market") or {}).get("20d")
            if isinstance(row.get("rs_vs_market"), dict) else row.get("rs_vs_market"),
            "bar_source": row.get("source") or row.get("bar_source"),
            "quote_source": row.get("quote_source") or row.get("price_source"),
            "as_of": row.get("as_of"),
            "bars_since_alignment": row.get("bars_since_alignment"),
        },
        "blockers": _blockers(row),
    }


def _blockers(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if not row.get("history_ok", True):
        out.append("insufficient history")
    if (row.get("entry") or {}).get("eligibility") in ("ENTRY_EXPIRED", "ENTRY_INVALIDATED"):
        out.append(str((row.get("entry") or {}).get("reason") or "entry not current"))
    if row.get("extended"):
        out.append("beyond the chase limit")
    if not row.get("source") and not row.get("bar_source"):
        out.append("bar source unknown")
    return out


def from_idea(candidate: dict[str, Any]) -> dict[str, Any]:
    """Build the contract from a Trade Ideas candidate."""
    row = {
        "symbol": candidate.get("symbol"), "company": candidate.get("company"),
        "sector_symbol": candidate.get("sector_symbol"), "direction": candidate.get("direction"),
        "horizon": candidate.get("horizon"), "momentum": candidate.get("momentum"),
        "trend": candidate.get("trend"), "phase": candidate.get("phase"),
        "rs_vs_parent": candidate.get("rs_vs_parent"), "rs_vs_market": candidate.get("rs_vs_market"),
        "as_of": candidate.get("as_of"), "rule_version": candidate.get("rule_version"),
        "bars_since_alignment": candidate.get("bars_since_alignment"),
        "instrument_evaluation": candidate.get("instrument_evaluation"),
        "extended": candidate.get("extended"),
        "entry": {
            "state": candidate.get("entry_state"), "playbook": candidate.get("playbook"),
            "trigger": candidate.get("trigger"), "invalidation": candidate.get("invalidation"),
            "target": candidate.get("target"), "reward_risk": candidate.get("reward_risk"),
            "chase_limit": candidate.get("chase_limit"),
            "eligibility": candidate.get("eligibility"),
            "reason": candidate.get("entry_reason"),
        },
    }
    payload = from_scan_row(row)
    payload["research_state"] = ("BEARISH_RESEARCH" if candidate.get("direction") == "SHORT"
                                 else "QUALIFIED_RESEARCH")
    payload["bucket"] = candidate.get("bucket")
    return payload
