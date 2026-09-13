"""Accept only exact evidence claims, not free-form AI trading advice."""
from hashlib import sha256
import json
from typing import Any


def validate_evidence_claims(snapshot: dict[str, Any], output: dict[str, Any]) -> list[dict[str, Any]]:
    facts = snapshot["facts"]
    identity = sha256(json.dumps(facts, sort_keys=True, allow_nan=False).encode()).hexdigest()
    if snapshot.get("schema_version") != "qx.mover-evidence.v1" or snapshot.get("snapshot_id") != identity:
        raise ValueError("Invalid snapshot identity")
    if set(output) != {"snapshot_id", "claims"} or output["snapshot_id"] != identity:
        raise ValueError("Unbound interpretation")
    claims = output["claims"]
    if not isinstance(claims, list) or len(claims) > len(facts):
        raise ValueError("Invalid claims")
    seen: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {"field", "value"}:
            raise ValueError("Unsupported claim format")
        field = claim["field"]
        if not isinstance(field, str) or field not in facts or field in seen or facts[field] is None:
            raise ValueError("Missing or duplicate evidence")
        if json.dumps(claim["value"], sort_keys=True, allow_nan=False) != json.dumps(facts[field], sort_keys=True, allow_nan=False):
            raise ValueError("Claim differs from evidence")
        seen.add(field)
    return claims
