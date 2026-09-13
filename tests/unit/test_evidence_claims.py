import pytest
from qx.market.mover_briefing import mover_briefing
from qx.market.interpretation_validation import validate_evidence_claims
from tests.unit.test_market_movers_validation import candidate, bars


def test_claim_must_equal_bound_snapshot():
    snapshot = mover_briefing(candidate(bars()))
    claim = {"snapshot_id": snapshot["snapshot_id"], "claims": [{"field": "price", "value": snapshot["facts"]["price"]}]}
    assert validate_evidence_claims(snapshot, claim) == claim["claims"]
    claim["claims"][0]["value"] = -1
    with pytest.raises(ValueError):
        validate_evidence_claims(snapshot, claim)


def test_invented_fields_and_free_text_rejected():
    snapshot = mover_briefing(candidate(bars()))
    for output in [
        {"snapshot_id": snapshot["snapshot_id"], "claims": [{"field": "win_probability", "value": .99}]},
        {"snapshot_id": snapshot["snapshot_id"], "claims": [], "advice": "buy"},
        {"snapshot_id": "wrong", "claims": []},
    ]:
        with pytest.raises(ValueError):
            validate_evidence_claims(snapshot, output)
