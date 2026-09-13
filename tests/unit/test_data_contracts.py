import pytest

from qx.market.data_contracts import FACETS, SOURCES, assess_facets, source_contract


def test_every_facet_has_unique_identity_and_declares_limits():
    assert len({facet.key for facet in FACETS}) == len(FACETS)
    assert all(facet.label and facet.required_artifacts and facet.limitations for facet in FACETS)


def test_futures_context_requires_contract_continuity_and_cash_alignment():
    readiness = {item.key: item for item in assess_facets({"fresh_futures_quote": True})}
    context = readiness["futures_context"]
    assert context.status == "blocked"
    assert context.missing_artifacts == ("explicit_contract_history", "continuous_mapping", "cash_session_alignment")


def test_complete_intraday_artifacts_only_make_the_evidence_facet_ready():
    artifacts = {
        "fresh_futures_quote": True,
        "five_minute_bars": True,
        "explicit_contract_history": True,
        "cash_session_alignment": True,
    }
    readiness = {item.key: item for item in assess_facets(artifacts)}
    assert readiness["intraday_structure"].status == "ready"
    assert readiness["options_flow"].status == "blocked"


def test_source_registry_is_resolvable_and_rejects_unknown_sources():
    assert source_contract("bls_calendar").access == "public"
    assert {source.key for source in SOURCES} >= {"schwab_market_data", "fomc_calendar"}
    with pytest.raises(KeyError, match="Unknown"):
        source_contract("invented")
