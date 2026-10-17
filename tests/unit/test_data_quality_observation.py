from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from qx.models.rules import PublicationState, RuleResult, RuleSeverity, SignalState
from qx.pipeline.data_quality_observation import (
    analyze_canonical_observations,
    build_structure_profile,
    evaluate_visibility,
    summarize_snapshot_coverage,
)
from qx.pipeline.models import DataDependencyStatus, LifecycleState, QXEvaluationResult
from qx.playbooks.base import PlaybookEvaluation


NOW = datetime(2026, 9, 16, 18, 30, tzinfo=timezone.utc)


def test_visibility_requires_data_and_retrieval_at_or_before_evaluation() -> None:
    assert evaluate_visibility(NOW, NOW, NOW) == []
    assert evaluate_visibility(NOW + timedelta(seconds=1), NOW, NOW) == [
        "DATA_AS_OF_AFTER_EVALUATION"
    ]
    assert evaluate_visibility(NOW, NOW + timedelta(seconds=1), NOW) == [
        "RETRIEVED_AT_AFTER_EVALUATION"
    ]


def test_snapshot_coverage_blocks_only_on_observed_causality_violation() -> None:
    summary = summarize_snapshot_coverage(
        [
            {
                "kind": "bars",
                "available": True,
                "stale": True,
                "provider_failure": False,
                "causality_violations": [],
            },
            {
                "kind": "quotes",
                "available": False,
                "stale": False,
                "provider_failure": True,
                "causality_violations": [],
            },
        ]
    )

    assert summary["status"] == "PASS"
    assert summary["coverage"]["bars"]["coverage_pct"] == 100.0
    assert summary["coverage"]["quotes"]["coverage_pct"] == 0.0
    assert summary["stale_count"] == 1
    assert summary["provider_failure_count"] == 1


def test_snapshot_coverage_blocks_on_any_causality_violation() -> None:
    summary = summarize_snapshot_coverage(
        [
            {
                "kind": "options",
                "available": True,
                "stale": False,
                "provider_failure": False,
                "causality_violations": ["RETRIEVED_AT_AFTER_EVALUATION"],
            }
        ]
    )

    assert summary["status"] == "BLOCK"
    assert summary["causality_violation_count"] == 1


def test_observation_analysis_preserves_actual_reasons_and_gate_failures() -> None:
    watch = _result(LifecycleState.WATCH, NOW)
    armed = _result(LifecycleState.ARMED, NOW + timedelta(minutes=5))

    analysis = analyze_canonical_observations([watch, armed])

    assert analysis["lifecycle_distribution"] == {"ARMED": 1, "WATCH": 1}
    assert analysis["transition_counts"] == {"WATCH->ARMED": 1}
    playbook = analysis["playbooks"]["playbook_a_pullback"]
    assert playbook["evaluated"] == 2
    assert playbook["watch"] == 1
    assert playbook["armed"] == 1
    assert playbook["most_common_failed_hard_gate"] == "structure_gate"
    assert playbook["most_common_weak_evidence_factor"] == "coverage_factor"
    assert analysis["scarcity_categories"]["C_STRUCTURE"] == {"structure_gate": 2}


def test_no_setup_does_not_attribute_unconsumed_downstream_dependencies() -> None:
    result = _result(LifecycleState.NO_SETUP, NOW)
    result.playbooks = []
    result.primary_playbook_candidate = None
    result.data_dependencies = {
        "option_chain": DataDependencyStatus(
            name="option_chain",
            reason_code="OPTION_CHAIN_UNAVAILABLE_AT_EVALUATION_TIMESTAMP",
        ),
        "account_snapshot": DataDependencyStatus(
            name="account_snapshot",
            reason_code="ACCOUNT_SNAPSHOT_UNAVAILABLE_AT_EVALUATION_TIMESTAMP",
        ),
    }

    analysis = analyze_canonical_observations([result])

    assert analysis["no_setup_reason_frequencies"] == {"NO_REASON_RECORDED": 1}
    assert analysis["scarcity_categories"]["A_DATA_QUALITY"] == {}


def test_structure_profile_reports_repeated_scans_and_skips_non_numeric_latency() -> None:
    profile = build_structure_profile(
        [
            {
                "symbol": "SPY",
                "timeframe": "5m",
                "structure_ms": 2.0,
                "bars_processed": 50,
                "source_bar_count": 51,
                "pivot_calculation_calls": 1,
                "protected_swing_calculation_calls": 2,
                "confirmed_pivots": 4,
                "protected_swings": 1,
                "bos_events": 1,
                "choch_events": 0,
                "peak_traced_bytes": 100,
            },
            {
                "symbol": "SPY",
                "timeframe": "5m",
                "structure_ms": 4.0,
                "bars_processed": 51,
                "source_bar_count": 51,
                "pivot_calculation_calls": 1,
                "protected_swing_calculation_calls": 2,
                "confirmed_pivots": 5,
                "protected_swings": 2,
                "bos_events": 1,
                "choch_events": 1,
                "peak_traced_bytes": 0,
            },
        ],
        elapsed_seconds=1.0,
    )

    assert profile["latency"]["p50_ms"] == 3.0
    assert profile["bars_processed"] == 101
    assert profile["distinct_source_bars"] == 51
    assert profile["repeated_scan_bar_count"] == 50
    assert profile["scan_amplification"] == 101 / 51
    assert profile["pivot_calculation_calls"] == 2
    assert profile["protected_swing_calculation_calls"] == 4
    assert profile["throughput"] == {
        "observations": 2,
        "elapsed_seconds": 1.0,
        "observations_per_second": 2.0,
    }


def _result(state: LifecycleState, timestamp: datetime) -> QXEvaluationResult:
    market_regime = SimpleNamespace(trend="TREND_UP", session="OPENING")
    rules = [
        RuleResult(
            rule_id="structure_gate",
            category="STRUCTURE",
            required_value=True,
            observed_value=False,
            passed=False,
            severity=RuleSeverity.HARD,
            hard_gate=True,
        ),
        RuleResult(
            rule_id="coverage_factor",
            category="EVIDENCE_COVERAGE",
            required_value=0.75,
            observed_value=0.5,
            passed=False,
            severity=RuleSeverity.SOFT,
            hard_gate=False,
        ),
    ]
    playbook = PlaybookEvaluation.model_construct(
        playbook_id="playbook_a_pullback",
        symbol="SPY",
        timeframe="5m",
        state=SignalState.WATCH if state == LifecycleState.WATCH else SignalState.ARMED,
        reason_code="STRUCTURE_GATE_FAILED",
        market_regime=market_regime,
        rule_results=rules,
    )
    return QXEvaluationResult.model_construct(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=timestamp,
        publication_state=PublicationState.RESEARCH_ONLY,
        structure=SimpleNamespace(regime="BULLISH"),
        market_regime=market_regime,
        direction=SimpleNamespace(coverage_status="PARTIAL"),
        playbooks=[playbook],
        primary_playbook_candidate=playbook,
        trigger=None,
        tradeability=None,
        options_expression=None,
        portfolio_risk=None,
        current_lifecycle_state=state,
        evidence_summary=[],
        reason_codes=[],
        config_version="research_v1",
        pipeline_version="core_v1",
        engine_versions={},
        stage_latencies={},
        data_dependencies={},
        io_metrics=[],
    )
