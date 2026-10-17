"""Trade Ideas: one aggregated candidate set across the scanned universe.

Design notes
------------
Aggregating live is far too slow: fetching bars for one sector's 25 members costs
~25 s (the three studies together are only ~0.06 s per symbol — the cost is the
market-data round trip). Aggregating all 23 sectors on page load would take
minutes, so ideas are built into a **snapshot** by a background job and the page
reads the snapshot. The snapshot always carries its own age and membership
provenance, so a stale set is visible rather than silently presented as live.

This is deliberately ONE candidate set with several VIEWS, not several scanners
with their own rules. A candidate is a shared record; a view is a filter over it.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
from typing import Any

from qx.core.atomic_store import (
    STATUS_CORRUPT,
    STATUS_MISSING,
    JobClaim,
    atomic_write_json,
    read_json,
)
from qx.explorer import membership, service

WORKSPACE_ROOT = os.environ.get("QX_WORKSPACE_ROOT", "").strip() or r"C:\Project\2026"
SNAPSHOT_PATH = os.path.join(WORKSPACE_ROOT, "data", "cache", "trade_ideas", "snapshot.json")
SNAPSHOT_TTL_SECONDS = 6 * 3600

ENTRY = {
    service.ENTRY_TRIGGER: "ready_now",
    service.ENTRY_BREAKOUT: "near_trigger",
    service.ENTRY_PULLBACK: "pullback_watch",
    service.ENTRY_EXTENDED: "extended_wait",
    service.ENTRY_BLOCKED_DATA: "insufficient",
    service.ENTRY_BLOCKED_RESISTANCE: "blocked",
    service.ENTRY_NONE: "insufficient",
}

# The five views required by the brief. Each is a filter over the SAME records.
VIEWS = (
    ("ready_now", "Ready now", "a plan is live under the entry engine's own latch"),
    ("near_trigger", "Near trigger", "structure present, entry candle not yet printed"),
    ("pullback_watch", "Pullback watch", "building inside the structure; waiting for a pullback"),
    ("newly_aligned", "Newly aligned", "discovery candidates — NOT qualified trades"),
    ("bearish", "Bearish opportunities", "momentum down and trend down"),
)

_LOCK = threading.Lock()
# F19: the job latch is a JobClaim so the check-and-set is atomic. Previously
# build_async tested `running` OUTSIDE the lock and then started a thread, so two
# concurrent callers could both pass the test and both launch a build.
_BUILDING = JobClaim(("started_at", "done", "total", "current", "error"))


def status() -> dict[str, Any]:
    result = _read_snapshot_result()
    snapshot = result.payload if result.ok and isinstance(result.payload, dict) else None
    return {
        "has_snapshot": snapshot is not None,
        # F19: corruption is reported as its own condition. It previously looked
        # identical to "no snapshot yet", which hid a damaged file.
        "snapshot_status": result.status,
        "snapshot_error": result.error,
        "snapshot_age_seconds": _age_seconds(snapshot),
        "stale": _is_stale(snapshot),
        "generated_at": (snapshot or {}).get("generated_at"),
        "candidates": len((snapshot or {}).get("candidates") or []),
        "building": _BUILDING.snapshot(),
    }


def _age_seconds(snapshot: dict[str, Any] | None) -> float | None:
    if not snapshot or not snapshot.get("generated_at"):
        return None
    try:
        when = dt.datetime.fromisoformat(str(snapshot["generated_at"]))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return round((dt.datetime.now(dt.timezone.utc) - when).total_seconds(), 1)


def _is_stale(snapshot: dict[str, Any] | None) -> bool:
    age = _age_seconds(snapshot)
    return age is None or age > SNAPSHOT_TTL_SECONDS


def _read_snapshot_result() -> Any:
    """Read the snapshot WITH its status, so corruption is not read as absence (F19)."""
    return read_json(SNAPSHOT_PATH)


def _read_snapshot() -> dict[str, Any] | None:
    """Back-compatible accessor: the payload, or None when missing OR corrupt."""
    result = _read_snapshot_result()
    return result.payload if result.ok and isinstance(result.payload, dict) else None


def _write_snapshot(payload: dict[str, Any]) -> None:
    """Atomic write (F19): a crash cannot leave a half-written snapshot."""
    atomic_write_json(SNAPSHOT_PATH, payload)


# --------------------------------------------------------------------------- #
# Building the candidate set
# --------------------------------------------------------------------------- #

def _candidate(row: dict[str, Any], sector_symbol: str, sector_name: str,
               universe: str) -> dict[str, Any]:
    entry = row.get("entry") or {}
    state = entry.get("state") or service.ENTRY_NONE
    rs_parent = (row.get("rs_vs_parent") or {}).get("20d")
    rs_market = (row.get("rs_vs_market") or {}).get("20d")
    # F12: a pullback is Boyd phase 4, carried through so the Ideas view can use the
    # SAME definition as the explorer rather than re-deriving a different one.
    is_pullback = bool(row.get("is_pullback"))
    return {
        "symbol": row.get("symbol"),
        "company": row.get("company"),
        "sector_symbol": sector_symbol,
        "sector_name": sector_name,
        "universe": universe,
        "weight": row.get("weight"),
        "rank": row.get("rank"),
        "price": row.get("price"),
        "as_of": row.get("as_of"),
        "observed_at": row.get("observed_at"),
        "freshness": row.get("freshness"),
        "direction": "LONG" if row.get("aligned_up") else (
            "SHORT" if row.get("aligned_down") else "NEUTRAL"),
        "momentum": row.get("momentum"),
        "trend": row.get("trend"),
        "bars_since_alignment": row.get("bars_since_alignment"),
        "newly_aligned": row.get("newly_aligned"),
        "is_pullback": is_pullback,
        "phase": row.get("phase"),
        "phase_label": row.get("phase_label"),
        "rs_vs_parent": rs_parent,
        "rs_vs_market": rs_market,
        "rs_basis": row.get("rs_basis"),
        "entry_state": state,
        "eligibility": entry.get("eligibility"),
        "playbook": entry.get("playbook"),
        "trigger": entry.get("trigger"),
        "invalidation": entry.get("invalidation"),
        "target": entry.get("target"),
        "reward_risk": entry.get("reward_risk"),
        "chase_limit": entry.get("chase_limit"),
        "entry_reason": entry.get("reason"),
        "extended": row.get("extended"),
        "rvol": row.get("rvol"),
        "horizon": "SWING",
        "instrument_evaluation": "UNDERLYING_ONLY",
        "rule_version": row.get("rule_version"),
        "bucket": ENTRY.get(state, "insufficient"),
    }


def build(force: bool = False, sectors: list[str] | None = None,
          universe: str = membership.UNIVERSE_HOLDINGS) -> dict[str, Any]:
    """Build the candidate snapshot across the universe. Slow — run in background."""
    # F19: claim the job atomically. The check and the set happen under one lock, so
    # a second caller cannot slip through between them.
    if not _claim_build():
        return {"ok": False, "error": "a build is already running",
                "building": _BUILDING.snapshot()}
    return _run_build(sectors, universe)


def _claim_build() -> bool:
    """Atomically become the build owner. One lock for both the test and the set."""
    return _BUILDING.claim(
        started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        done=0, total=0, current=None, error=None)


def _run_build(sectors: list[str] | None, universe: str) -> dict[str, Any]:
    """The build body. Ownership must already have been claimed by the caller."""
    try:
        cat = service.catalog()
        targets: list[tuple[str, str]] = []
        for item in cat["sectors"]:
            targets.append((item["symbol"], item["name"]))
        for item in cat["industries"]:
            targets.append((item["symbol"], f"{item['name']} ({item['parent']})"))
        if sectors:
            wanted = {s.upper() for s in sectors}
            targets = [t for t in targets if t[0] in wanted]

        _BUILDING.update(total=len(targets))
        candidates: list[dict[str, Any]] = []
        sector_meta: list[dict[str, Any]] = []
        errors: list[str] = []
        seen: dict[str, dict[str, Any]] = {}

        for symbol, name in targets:
            _BUILDING.update(current=symbol)
            try:
                data = service.explore(symbol, universe, view="all", limit=200)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{symbol}: {type(exc).__name__}: {str(exc)[:80]}")
                _BUILDING.increment("done")
                continue

            sector_meta.append({
                "symbol": symbol, "name": name,
                "universe": data["membership"]["universe"],
                "membership_status": data["membership"]["status"],
                "weight_covered_pct": data["membership"].get("weight_covered_pct"),
                "is_partial": data["membership"].get("is_partial"),
                "breadth": data["breadth"],
                "parent_momentum": data["parent"].get("momentum"),
                "parent_trend": data["parent"].get("trend"),
                "rules": data["rules"],
            })
            for row in data["rows"]:
                candidate = _candidate(row, symbol, name, data["membership"]["universe"])
                if not candidate["symbol"]:
                    continue
                # F18: a name can sit in several ETFs, so membership is a RELATION, not
                # a single field. Record EVERY membership with its own per-parent
                # metrics, then pick the primary parent by a DECLARED policy — the old
                # code claimed "highest-conviction sector" but actually kept whichever
                # sector happened to be iterated first, so a name first seen under XLK
                # vanished when filtering its SMH membership.
                membership_entry = {
                    "sector_symbol": symbol,
                    "sector_name": name,
                    "weight": candidate.get("weight"),
                    "rank": candidate.get("rank"),
                    "rs_vs_parent": candidate.get("rs_vs_parent"),
                    "is_partial": data["membership"].get("is_partial"),
                    "coverage_label": data["membership"].get("coverage_label"),
                }
                existing = seen.get(candidate["symbol"])
                if existing is not None:
                    existing["memberships"].append(membership_entry)
                    continue
                candidate["memberships"] = [membership_entry]
                seen[candidate["symbol"]] = candidate
                candidates.append(candidate)
            _BUILDING.increment("done")

        # Resolve each candidate's primary parent deterministically, once all
        # memberships are known.
        for candidate in candidates:
            _resolve_primary_parent(candidate)

        payload = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "universe": universe,
            "sectors_scanned": len(sector_meta),
            "candidates": candidates,
            "sectors": sector_meta,
            "errors": errors,
            "rules": {"momo_trend": "tops_multitrend_v4",
                      "phases": "james_boyd_5_phases_v1",
                      "entry": "qx_master_auto_fast_v5_2_4"},
        }
        _write_snapshot(payload)
        return {"ok": True, "candidates": len(candidates), "sectors": len(sector_meta)}
    except Exception as exc:  # noqa: BLE001
        message = f"{type(exc).__name__}: {exc}"
        _BUILDING.update(error=message)
        return {"ok": False, "error": message}
    finally:
        _BUILDING.release()


def build_async(force: bool = False) -> dict[str, Any]:
    """Start a build in the background, claiming ownership ATOMICALLY (F19).

    The old version tested the running flag outside the lock and then spawned a
    thread, so two concurrent callers could both pass the test. Worse, it reported
    ``started: True`` even when the spawned build was doomed to be refused. Now the
    claim happens here, before the thread exists, and the answer is truthful.
    """
    if not _claim_build():
        return {"ok": False, "error": "a build is already running",
                "building": _BUILDING.snapshot()}
    thread = threading.Thread(target=_run_build, kwargs={"sectors": None, "universe": membership.UNIVERSE_HOLDINGS}, daemon=True)
    thread.start()
    return {"ok": True, "started": True}


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #

PRIMARY_PARENT_POLICY = (
    "highest fund weight; ties broken by strongest parent-relative 20-day strength, "
    "then by sector symbol alphabetically (fully deterministic)"
)


def _resolve_primary_parent(candidate: dict[str, Any]) -> None:
    """Choose ONE primary parent by a declared, deterministic policy (F18).

    Every membership is kept, so a sector filter can match ANY of them. The primary
    parent decides only which single set of parent metrics the row displays by
    default, and it is reproducible — never dependent on scan order.
    """
    memberships = candidate.get("memberships") or []
    if not memberships:
        return

    def sort_key(entry: dict[str, Any]) -> tuple:
        weight = entry.get("weight")
        rs = entry.get("rs_vs_parent")
        # Descending weight, descending RS, then ascending symbol for a stable order.
        return (-(weight if isinstance(weight, (int, float)) else -1.0),
                -(rs if isinstance(rs, (int, float)) else float("-inf")),
                str(entry.get("sector_symbol") or ""))

    ranked = sorted(memberships, key=sort_key)
    primary = ranked[0]
    for entry in memberships:
        entry["is_primary"] = entry is primary

    candidate["sector_symbol"] = primary.get("sector_symbol")
    candidate["sector_name"] = primary.get("sector_name")
    candidate["weight"] = primary.get("weight")
    candidate["rank"] = primary.get("rank")
    candidate["rs_vs_parent"] = primary.get("rs_vs_parent")
    candidate["membership_count"] = len(memberships)
    candidate["sector_symbols"] = sorted({str(m.get("sector_symbol")) for m in memberships
                                          if m.get("sector_symbol")})
    candidate["also_in"] = [s for s in candidate["sector_symbols"]
                            if s != candidate["sector_symbol"]]
    candidate["primary_parent_policy"] = PRIMARY_PARENT_POLICY


def _matches_sector(candidate: dict[str, Any], sector: str) -> bool:
    """Match ANY membership, not just the primary parent (F18)."""
    wanted = sector.upper()
    if candidate.get("sector_symbol") == wanted:
        return True
    return wanted in (candidate.get("sector_symbols") or [])


def _apply_view(candidates: list[dict[str, Any]], view: str) -> list[dict[str, Any]]:
    if view == "all":
        return candidates
    if view == "ready_now":
        return [c for c in candidates if c["bucket"] == "ready_now"]
    if view == "near_trigger":
        return [c for c in candidates if c["bucket"] == "near_trigger"]
    if view == "pullback_watch":
        # F12: use the SAME definition as the explorer (Boyd phase 4 or trend-up with
        # momentum not yet up), never a re-derived approximation.
        return [c for c in candidates if c.get("is_pullback")]
    if view == "newly_aligned":
        return [c for c in candidates if c.get("newly_aligned")]
    if view == "bearish":
        return [c for c in candidates if c["direction"] == "SHORT"]
    return candidates


SORTS = (
    ("entry_readiness", "Entry readiness", "ready now, then near trigger, then pullback"),
    ("newly_aligned", "Newly aligned", "most recent alignment first"),
    ("rs_parent", "Parent-relative strength", "20-day excess return vs its sector ETF"),
    ("rs_market", "Market-relative strength", "20-day excess return vs SPY"),
    ("distance_to_trigger", "Distance to trigger", "closest to firing first"),
)


def _sort(candidates: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    order = {"ready_now": 0, "near_trigger": 1, "pullback_watch": 2,
             "extended_wait": 3, "blocked": 4, "insufficient": 5}
    if sort == "newly_aligned":
        return sorted(candidates, key=lambda c: (not c.get("newly_aligned"),
                                                 c.get("bars_since_alignment") or 10**6))
    if sort == "rs_parent":
        return sorted(candidates, key=lambda c: (c.get("rs_vs_parent") is None,
                                                 -(c.get("rs_vs_parent") or 0)))
    if sort == "rs_market":
        return sorted(candidates, key=lambda c: (c.get("rs_vs_market") is None,
                                                 -(c.get("rs_vs_market") or 0)))
    if sort == "distance_to_trigger":
        def distance(c: dict[str, Any]) -> float:
            trigger, price = c.get("trigger"), c.get("price")
            if trigger is None or price is None or not price:
                return 10**9
            return abs(trigger - price) / price
        return sorted(candidates, key=distance)
    return sorted(candidates, key=lambda c: (order.get(c["bucket"], 9),
                                             -(c.get("rs_market") or 0)))


def ideas(view: str = "ready_now", sort: str = "entry_readiness",
          sector: str | None = None, limit: int = 200) -> dict[str, Any]:
    """Read the candidate snapshot. NEVER forces a quota — empty is a valid answer."""
    snapshot = _read_snapshot()
    if snapshot is None:
        return {
            "ok": True, "has_snapshot": False, "generated_at": None,
            "stale": True, "age_seconds": None, "view": view, "sort": sort,
            "counts": {vid: 0 for vid, _, _ in VIEWS},
            "views": [{"id": v, "label": l, "description": d, "count": 0} for v, l, d in VIEWS],
            "sorts": [{"id": s, "label": l, "description": d} for s, l, d in SORTS],
            "ideas": [], "row_count": 0, "shown": 0,
            "verdict": "NO_SNAPSHOT",
            "message": "No candidate snapshot yet. Build one from this page.",
            "building": _BUILDING.snapshot(),
        }

    candidates = list(snapshot.get("candidates") or [])
    if sector:
        # F18: filter on the membership RELATION, so a name held by both XLK and SMH
        # is found under either — previously only its primary parent matched.
        candidates = [c for c in candidates if _matches_sector(c, sector)]
    counts = {vid: len(_apply_view(candidates, vid)) for vid, _, _ in VIEWS}
    stale = _is_stale(snapshot)

    # Reviewer F09: staleness must GATE current readiness, not merely be flagged.
    # A stale snapshot stays browsable as research history, but ready_now is emptied
    # so a latched old signal can never be presented as actionable.
    if stale:
        counts["ready_now"] = 0
        counts["near_trigger"] = 0
        candidates_actionable = []
    else:
        candidates_actionable = candidates

    selected = _sort(_apply_view(candidates_actionable if view in ("ready_now", "near_trigger")
                                 else candidates, view), sort)[:limit]
    total = len(candidates)

    if stale:
        verdict = "SNAPSHOT_STALE" if view in ("ready_now", "near_trigger") else "SNAPSHOT_STALE_HISTORY"
        message = (f"Snapshot is {round((_age_seconds(snapshot) or 0) / 60)} min old (TTL "
                   f"{SNAPSHOT_TTL_SECONDS // 3600}h). Current-readiness views are emptied: "
                   "a stale latch is not an actionable idea. Rebuild to refresh.")
    elif selected:
        verdict = "IDEAS_AVAILABLE"
        message = None
    else:
        verdict = "NOTHING_QUALIFIES"
        message = "Nothing qualifies in this view. No ideas are manufactured to fill the page."

    return {
        "ok": True,
        "has_snapshot": True,
        "generated_at": snapshot.get("generated_at"),
        "age_seconds": _age_seconds(snapshot),
        "stale": stale,
        "universe": snapshot.get("universe"),
        "sectors_scanned": snapshot.get("sectors_scanned"),
        "view": view,
        "sort": sort,
        "sector": sector,
        "counts": counts,
        "views": [{"id": v, "label": l, "description": d, "count": counts[v]} for v, l, d in VIEWS],
        "sorts": [{"id": s, "label": l, "description": d} for s, l, d in SORTS],
        "ideas": selected,
        "row_count": total,
        "shown": len(selected),
        "verdict": verdict,
        "message": message,
        "primary_parent_policy": PRIMARY_PARENT_POLICY,
        "multi_membership_count": sum(1 for c in candidates
                                      if (c.get("membership_count") or 1) > 1),
        "rules": snapshot.get("rules"),
        "errors": snapshot.get("errors") or [],
        "building": _BUILDING.snapshot(),
    }


def why_ranked(symbol: str, view: str = "ready_now", sort: str = "entry_readiness") -> dict[str, Any]:
    """Deterministic explanation of a candidate's position — no model, no opinion."""
    data = ideas(view=view, sort=sort, limit=500)
    ranked = data["ideas"]
    match = next((c for c in ranked if c["symbol"] == symbol.upper()), None)
    if match is None:
        return {"ok": False, "error": f"{symbol} is not in view {view!r}"}
    position = ranked.index(match) + 1
    reasons = [
        f"Position {position} of {len(ranked)} in view '{view}' sorted by '{sort}'.",
        f"Bucket {match['bucket']} (entry state {match['entry_state']}).",
    ]
    if sort == "entry_readiness":
        reasons.append("Entry-readiness order: ready now, then near trigger, then pullback watch.")
    if match.get("rs_market") is not None:
        reasons.append(f"Market-relative 20-day strength {match['rs_market']:+.2f}%.")
    if match.get("rs_parent") is not None:
        reasons.append(f"Parent-relative 20-day strength {match['rs_parent']:+.2f}%.")
    if match.get("bars_since_alignment") is not None:
        reasons.append(f"Alignment has held {match['bars_since_alignment']} bars.")
    return {"ok": True, "symbol": symbol.upper(), "position": position, "of": len(ranked),
            "view": view, "sort": sort, "candidate": match, "reasons": reasons,
            "note": "Ranking is deterministic and separated by concern; there is no single universal score."}
