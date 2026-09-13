"""Versioned evidence for interpretation; no model call or trade authorization."""
from dataclasses import asdict
from hashlib import sha256
import json
from typing import Any

from qx.market.movers import MarketMoverCandidate


def mover_briefing(candidate: MarketMoverCandidate) -> dict[str, Any]:
    values = asdict(candidate)
    keys = ("symbol", "bar_date", "actual_source", "freshness", "price", "return_1d",
            "relative_volume_20d", "avg_volume_20d", "dollar_volume", "close_location",
            "accumulation_ratio", "accumulation_score", "mover_score", "mover_action",
            "tape_status", "rectangle_signal", "options_quality")
    facts = {key: values[key] for key in keys}
    # Snapshot identity binds a future interpretation to exactly these facts.
    identity = sha256(json.dumps(facts, sort_keys=True, allow_nan=False).encode()).hexdigest()
    warnings = [
        "Scores are descriptive heuristics, not calibrated probabilities.",
        "Calendar alignment describes the scan time, not freshness at interpretation time.",
        "Rectangle context is historical and cannot confirm a current setup.",
        "Underlying liquidity does not establish option-contract liquidity.",
    ]
    if candidate.freshness != "Session-aligned" or candidate.actual_source == "unknown" or not candidate.bar_date:
        warnings.append("Source or session validation is incomplete; do not describe this as actionable.")
    return {
        "schema_version": "qx.mover-evidence.v1", "snapshot_id": identity,
        "mode": "deterministic_evidence_only", "facts": facts,
        "unknown": ["earnings_date", "event_risk", "option_contract_quotes", "execution_spread",
                    "current_quote", "out_of_sample_success_rate"],
        "warnings": warnings,
        "interpretation_contract": {
            "required_citations": "facts.<field> plus snapshot_id for every market assertion",
            "allowed": ["explain existing classifications", "identify conflicting evidence", "list missing checks"],
            "prohibited": ["invent missing facts", "change rule outcomes", "claim a win probability", "place trades"],
        },
    }
