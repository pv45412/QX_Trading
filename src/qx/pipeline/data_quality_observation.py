"""Observational summaries for the DQ2-DQ6 validation milestone."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from qx.pipeline.models import LifecycleState, QXEvaluationResult, SKIPPED
from qx.pipeline.performance import latency_distribution, replay_throughput
from qx.pipeline.point_in_time import aware_utc, parse_timestamp


SNAPSHOT_KINDS = ("bars", "quotes", "options", "account")


def evaluate_visibility(
    data_as_of: Any,
    retrieved_at: Any,
    evaluation_timestamp: datetime,
) -> list[str]:
    """Return explicit causality violations without changing source timestamps."""
    evaluation = aware_utc(evaluation_timestamp)
    data_timestamp = parse_timestamp(data_as_of)
    retrieval_timestamp = parse_timestamp(retrieved_at)
    violations: list[str] = []
    if data_timestamp is None:
        violations.append("DATA_AS_OF_INVALID")
    elif data_timestamp > evaluation:
        violations.append("DATA_AS_OF_AFTER_EVALUATION")
    if retrieval_timestamp is None:
        violations.append("RETRIEVED_AT_INVALID")
    elif retrieval_timestamp > evaluation:
        violations.append("RETRIEVED_AT_AFTER_EVALUATION")
    return violations


def summarize_snapshot_coverage(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize independently measured provider coverage by snapshot kind."""
    by_kind: dict[str, dict[str, Any]] = {}
    all_violations: Counter[str] = Counter()
    for kind in SNAPSHOT_KINDS:
        selected = [item for item in observations if item.get("kind") == kind]
        available = sum(bool(item.get("available")) for item in selected)
        stale = sum(bool(item.get("stale")) for item in selected)
        missing = sum(not bool(item.get("available")) for item in selected)
        failures = sum(bool(item.get("provider_failure")) for item in selected)
        violations = Counter(
            violation
            for item in selected
            for violation in item.get("causality_violations", ())
        )
        all_violations.update(violations)
        by_kind[kind] = {
            "total": len(selected),
            "available": available,
            "coverage_pct": _percentage(available, len(selected)),
            "stale": stale,
            "missing": missing,
            "provider_failures": failures,
            "causality_violations": sum(violations.values()),
            "causality_violation_reasons": dict(sorted(violations.items())),
        }
    provider_failures = sum(bool(item.get("provider_failure")) for item in observations)
    return {
        "status": "BLOCK" if all_violations else "PASS",
        "total_observations": len(observations),
        "coverage": by_kind,
        "stale_count": sum(bool(item.get("stale")) for item in observations),
        "missing_count": sum(not bool(item.get("available")) for item in observations),
        "provider_failure_count": provider_failures,
        "causality_violation_count": sum(all_violations.values()),
        "causality_violation_reasons": dict(sorted(all_violations.items())),
    }


def analyze_canonical_observations(
    results: Sequence[QXEvaluationResult],
) -> dict[str, Any]:
    """Aggregate lifecycle and evidence diagnostics without changing rule semantics."""
    ordered = sorted(
        results,
        key=lambda item: (item.symbol, item.timeframe, item.evaluation_timestamp),
    )
    lifecycle = Counter(_value(result.current_lifecycle_state) for result in ordered)
    transitions: Counter[str] = Counter()
    prior_by_series: dict[tuple[str, str], str] = {}
    no_setup_reasons: Counter[str] = Counter()
    blocked_reasons: Counter[str] = Counter()
    regime_counts: Counter[str] = Counter()
    session_counts: Counter[str] = Counter()
    pipeline_versions = Counter(result.pipeline_version for result in ordered)
    category_reasons: dict[str, Counter[str]] = {
        key: Counter()
        for key in (
            "A_DATA_QUALITY",
            "B_EVIDENCE_COVERAGE",
            "C_STRUCTURE",
            "D_REGIME",
            "E_DIRECTION",
            "F_PLAYBOOK_GATES",
            "G_TRIGGER",
            "H_TRADEABILITY",
            "I_OPTIONS_EXPRESSION",
            "J_PORTFOLIO_RISK",
        )
    }
    playbooks: dict[str, dict[str, Any]] = {}

    for result in ordered:
        state = _value(result.current_lifecycle_state)
        series = (result.symbol, result.timeframe)
        prior = prior_by_series.get(series)
        if prior is not None and prior != state:
            transitions[f"{prior}->{state}"] += 1
        prior_by_series[series] = state

        regime = _value(getattr(result.market_regime, "trend", "UNAVAILABLE"))
        session = _value(getattr(result.market_regime, "session", "UNAVAILABLE"))
        regime_counts[regime] += 1
        session_counts[session] += 1

        dependency_reasons = []
        for dependency_name, dependency in result.data_dependencies.items():
            reason = getattr(dependency, "reason_code", None)
            if reason:
                dependency_reasons.append(str(reason))
                if dependency_name == "bars" or (
                    state == LifecycleState.BLOCKED.value
                    and str(reason) in result.reason_codes
                ):
                    category_reasons["A_DATA_QUALITY"][str(reason)] += 1

        coverage_status = _value(
            getattr(result.direction, "coverage_status", "UNAVAILABLE")
        )
        if coverage_status in {"UNAVAILABLE", "INSUFFICIENT", "PARTIAL"}:
            category_reasons["B_EVIDENCE_COVERAGE"][coverage_status] += 1

        result_reasons = list(result.reason_codes)
        if state == LifecycleState.NO_SETUP.value:
            reasons = _playbook_reasons(result) or result_reasons or ["NO_REASON_RECORDED"]
            no_setup_reasons.update(reasons)
        if state == LifecycleState.BLOCKED.value:
            blocked_reasons.update(result_reasons or dependency_reasons or ["NO_REASON_RECORDED"])

        for evaluation in result.playbooks or ():
            playbook_id = str(evaluation.playbook_id)
            summary = playbooks.setdefault(
                playbook_id,
                {
                    "evaluated": 0,
                    "state_counts": Counter(),
                    "failed_hard_gates": Counter(),
                    "weak_evidence_factors": Counter(),
                    "regime_counts": Counter(),
                    "session_counts": Counter(),
                    "reason_counts": Counter(),
                },
            )
            summary["evaluated"] += 1
            summary["state_counts"][_value(evaluation.state)] += 1
            summary["regime_counts"][regime] += 1
            summary["session_counts"][session] += 1
            if evaluation.reason_code:
                summary["reason_counts"][evaluation.reason_code] += 1
                category_reasons["F_PLAYBOOK_GATES"][evaluation.reason_code] += 1
            for rule in evaluation.rule_results:
                if rule.passed:
                    continue
                if rule.hard_gate:
                    summary["failed_hard_gates"][rule.rule_id] += 1
                else:
                    summary["weak_evidence_factors"][rule.rule_id] += 1
                _classify_rule_failure(category_reasons, rule)

        _add_stage_reasons(category_reasons, result)

    serialized_playbooks = {}
    for playbook_id, summary in sorted(playbooks.items()):
        states = summary["state_counts"]
        serialized_playbooks[playbook_id] = {
            "evaluated": summary["evaluated"],
            "watch": states["WATCH"],
            "armed": states["ARMED"],
            "state_counts": _sorted_counter(states),
            "failed_hard_gates": _sorted_counter(summary["failed_hard_gates"]),
            "most_common_failed_hard_gate": _most_common(summary["failed_hard_gates"]),
            "weak_evidence_factors": _sorted_counter(summary["weak_evidence_factors"]),
            "most_common_weak_evidence_factor": _most_common(
                summary["weak_evidence_factors"]
            ),
            "reason_counts": _sorted_counter(summary["reason_counts"]),
            "regime_counts": _sorted_counter(summary["regime_counts"]),
            "session_counts": _sorted_counter(summary["session_counts"]),
        }

    return {
        "total_observations": len(ordered),
        "pipeline_versions": _sorted_counter(pipeline_versions),
        "lifecycle_distribution": _sorted_counter(lifecycle),
        "transition_counts": _sorted_counter(transitions),
        "no_setup_reason_frequencies": _sorted_counter(no_setup_reasons),
        "blocked_reason_frequencies": _sorted_counter(blocked_reasons),
        "scarcity_categories": {
            category: _sorted_counter(reasons)
            for category, reasons in category_reasons.items()
        },
        "playbooks": serialized_playbooks,
        "regime_distribution": _sorted_counter(regime_counts),
        "session_distribution": _sorted_counter(session_counts),
    }


def build_structure_profile(
    series_samples: Sequence[Mapping[str, Any]],
    elapsed_seconds: float,
) -> dict[str, Any]:
    """Build a structure-only workload profile from measured replay samples."""
    latencies = [
        float(sample["structure_ms"])
        for sample in series_samples
        if _number(sample.get("structure_ms"))
    ]
    by_series: dict[str, dict[str, Any]] = {}
    for key, selected in _group_by_series(series_samples).items():
        series_latencies = [
            float(item["structure_ms"])
            for item in selected
            if _number(item.get("structure_ms"))
        ]
        by_series[key] = {
            **latency_distribution(series_latencies),
            "observations": len(selected),
            "bars_processed": sum(int(item.get("bars_processed", 0)) for item in selected),
            "distinct_source_bars": max(
                (int(item.get("source_bar_count", 0)) for item in selected),
                default=0,
            ),
            "confirmed_pivots": sum(int(item.get("confirmed_pivots", 0)) for item in selected),
            "protected_swings": sum(int(item.get("protected_swings", 0)) for item in selected),
            "pivot_calculation_calls": sum(
                int(item.get("pivot_calculation_calls", 0)) for item in selected
            ),
            "protected_swing_calculation_calls": sum(
                int(item.get("protected_swing_calculation_calls", 0))
                for item in selected
            ),
            "bos_events": sum(int(item.get("bos_events", 0)) for item in selected),
            "choch_events": sum(int(item.get("choch_events", 0)) for item in selected),
            "peak_traced_bytes": max(
                (int(item.get("peak_traced_bytes", 0)) for item in selected),
                default=0,
            ),
        }
    total_bars_processed = sum(int(item.get("bars_processed", 0)) for item in series_samples)
    distinct_source_bars = sum(
        summary["distinct_source_bars"] for summary in by_series.values()
    )
    return {
        "latency": latency_distribution(latencies),
        "throughput": replay_throughput(len(series_samples), elapsed_seconds),
        "structure_evaluations": len(series_samples),
        "bars_processed": total_bars_processed,
        "distinct_source_bars": distinct_source_bars,
        "repeated_scan_bar_count": max(total_bars_processed - distinct_source_bars, 0),
        "scan_amplification": (
            total_bars_processed / distinct_source_bars if distinct_source_bars else None
        ),
        "pivot_calculation_calls": sum(
            int(item.get("pivot_calculation_calls", 0)) for item in series_samples
        ),
        "protected_swing_calculation_calls": sum(
            int(item.get("protected_swing_calculation_calls", 0))
            for item in series_samples
        ),
        "confirmed_pivots": sum(
            int(item.get("confirmed_pivots", 0)) for item in series_samples
        ),
        "protected_swings": sum(
            int(item.get("protected_swings", 0)) for item in series_samples
        ),
        "bos_events": sum(int(item.get("bos_events", 0)) for item in series_samples),
        "choch_events": sum(int(item.get("choch_events", 0)) for item in series_samples),
        "peak_traced_bytes": max(
            (int(item.get("peak_traced_bytes", 0)) for item in series_samples),
            default=0,
        ),
        "per_symbol_timeframe": by_series,
    }


def _add_stage_reasons(
    categories: dict[str, Counter[str]], result: QXEvaluationResult
) -> None:
    trigger = result.trigger
    if trigger is not None and _value(getattr(trigger, "state", "")) != "TRIGGERED":
        reasons = _rule_failures(getattr(trigger, "rule_results", ()))
        categories["G_TRIGGER"].update(reasons or ["TRIGGER_NOT_CONFIRMED"])
    if result.tradeability is not None:
        reasons = list(getattr(result.tradeability, "reason_codes", ()) or ())
        if reasons:
            categories["H_TRADEABILITY"].update(reasons)
    if result.options_expression is not None:
        reasons = list(getattr(result.options_expression, "reason_codes", ()) or ())
        if reasons:
            categories["I_OPTIONS_EXPRESSION"].update(reasons)
    if result.portfolio_risk is not None:
        reasons = list(getattr(result.portfolio_risk, "reason_codes", ()) or ())
        if reasons:
            categories["J_PORTFOLIO_RISK"].update(reasons)


def _classify_rule_failure(categories: dict[str, Counter[str]], rule: Any) -> None:
    category = str(getattr(rule, "category", "")).upper()
    target = "F_PLAYBOOK_GATES"
    if "STRUCT" in category:
        target = "C_STRUCTURE"
    elif "REGIME" in category or "SESSION" in category:
        target = "D_REGIME"
    elif "DIRECTION" in category:
        target = "E_DIRECTION"
    elif "EVIDENCE" in category or "COVERAGE" in category:
        target = "B_EVIDENCE_COVERAGE"
    categories[target][str(rule.rule_id)] += 1


def _playbook_reasons(result: QXEvaluationResult) -> list[str]:
    return [
        str(item.reason_code)
        for item in result.playbooks or ()
        if getattr(item, "reason_code", None)
    ]


def _rule_failures(rules: Iterable[Any]) -> list[str]:
    return [str(rule.rule_id) for rule in rules if not bool(getattr(rule, "passed", False))]


def _group_by_series(
    samples: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for sample in samples:
        grouped[
            f"{sample.get('symbol', 'UNKNOWN')}:{sample.get('timeframe', 'UNKNOWN')}"
        ].append(sample)
    return dict(sorted(grouped.items()))


def _most_common(counter: Counter[str]) -> str | None:
    if not counter:
        return None
    highest = max(counter.values())
    return sorted(key for key, value in counter.items() if value == highest)[0]


def _sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def _percentage(numerator: int, denominator: int) -> float | None:
    return round((numerator / denominator) * 100.0, 2) if denominator else None


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value != SKIPPED
