"""Observational analytics over canonical HistoricalReplayAdapter results."""

from __future__ import annotations

from datetime import datetime
from statistics import fmean
from typing import Any, Iterable, Optional

import pandas as pd
from pydantic import BaseModel, Field

from qx.pipeline.adapters import HistoricalReplayAdapter
from qx.pipeline.models import PIPELINE_VERSION, LifecycleState, QXEvaluationResult, SKIPPED
from qx.pipeline.point_in_time import bar_timestamp


TRIGGERED_STATES = {
    LifecycleState.BLOCKED,
    LifecycleState.TRIGGERED,
    LifecycleState.NOT_TRADEABLE,
    LifecycleState.TRADEABLE,
    LifecycleState.OPTIONS_NOT_SUITABLE,
    LifecycleState.OPTIONS_SUITABLE,
    LifecycleState.PORTFOLIO_VETOED,
    LifecycleState.PORTFOLIO_APPROVED,
}


class ReplayObservation(BaseModel):
    symbol: str
    timeframe: str
    timestamp: datetime
    session_date: str
    publication_state: str
    trend_regime: str = "UNKNOWN"
    volatility_regime: str = "UNKNOWN"
    gamma_regime: str = "UNKNOWN"
    session_regime: str = "UNKNOWN"
    direction_score: Optional[float] = None
    direction_label: Optional[str] = None
    direction_coverage: Optional[float] = None
    coverage_status: str = "UNAVAILABLE"
    evidence_coverage_bucket: str = "UNAVAILABLE"
    playbook: Optional[str] = None
    lifecycle_state: LifecycleState
    trigger_price: Optional[float] = None
    invalidation_price: Optional[float] = None
    tradeability_state: str = "UNAVAILABLE"
    observed_entry_reference_price: Optional[float] = None
    options_state: str = "UNAVAILABLE"
    portfolio_state: str = "UNAVAILABLE"
    option_snapshot_id: Optional[int] = None
    account_snapshot_id: Optional[int] = None
    option_snapshot_source: str = "UNAVAILABLE"
    account_snapshot_source: str = "UNAVAILABLE"
    market_driver_status: str = "UNAVAILABLE"
    primary_driver: str = "UNAVAILABLE"
    driver_strength: str = "UNAVAILABLE"
    driver_persistence_state: str = "UNAVAILABLE"
    driver_coverage_status: str = "UNAVAILABLE"
    reason_codes: list[str] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)
    stage_latencies: dict[str, float | int | str] = Field(default_factory=dict)
    engine_versions: dict[str, str] = Field(default_factory=dict)
    pipeline_version: str = PIPELINE_VERSION


class ReplayTransitionRecord(BaseModel):
    timestamp: datetime
    previous_state: LifecycleState
    new_state: LifecycleState
    pipeline_version: str = PIPELINE_VERSION


class ReplayOutcome(BaseModel):
    symbol: str
    timeframe: str
    playbook: Optional[str]
    direction: str
    setup_started_at: Optional[datetime] = None
    armed_at: Optional[datetime] = None
    triggered_at: Optional[datetime] = None
    ended_at: datetime
    outcome: str
    trigger_price: Optional[float] = None
    invalidation_price: Optional[float] = None
    target_price: Optional[float] = None
    tradeability_target_price: Optional[float] = None
    bars_to_trigger: Optional[int] = None
    seconds_to_trigger: Optional[float] = None
    bars_in_setup: int = 0
    seconds_in_setup: float = 0.0
    invalidation_before_trigger: bool = False
    false_trigger: bool = False
    ambiguous_same_bar: bool = False
    signal_risk: Optional[float] = None
    signal_mfe: Optional[float] = None
    signal_mae: Optional[float] = None
    signal_mfe_r: Optional[float] = None
    signal_mae_r: Optional[float] = None
    signal_endpoint_r: Optional[float] = None
    tradeability_entry_reference_price: Optional[float] = None
    tradeability_risk: Optional[float] = None
    tradeability_mfe: Optional[float] = None
    tradeability_mae: Optional[float] = None
    tradeability_mfe_r: Optional[float] = None
    tradeability_mae_r: Optional[float] = None
    tradeability_endpoint_r: Optional[float] = None
    trend_regime: str = "UNKNOWN"
    volatility_regime: str = "UNKNOWN"
    session_regime: str = "UNKNOWN"
    direction_label: str = "UNKNOWN"
    evidence_coverage_bucket: str = "UNAVAILABLE"
    primary_driver: str = "UNAVAILABLE"
    pipeline_version: str = PIPELINE_VERSION


class ReplaySegmentSummary(BaseModel):
    segment: str
    value: str
    setups: int
    triggered: int
    false_trigger_rate: Optional[float] = None
    invalidation_before_trigger_rate: Optional[float] = None
    average_signal_mfe_r: Optional[float] = None
    average_signal_mae_r: Optional[float] = None
    average_signal_endpoint_r: Optional[float] = None
    average_tradeability_mfe_r: Optional[float] = None
    average_tradeability_mae_r: Optional[float] = None
    average_tradeability_endpoint_r: Optional[float] = None


class ReplayReport(BaseModel):
    symbol: str
    timeframe: str
    started_at: datetime
    completed_at: datetime
    observations: list[ReplayObservation]
    transitions: list[ReplayTransitionRecord]
    outcomes: list[ReplayOutcome]
    segments: list[ReplaySegmentSummary]
    pipeline_version: str = PIPELINE_VERSION


def analyze_historical_replay(
    adapter: HistoricalReplayAdapter,
    historical_bars: Any,
    *,
    warmup_bars: int = 50,
    option_chain_snapshots: Optional[Iterable[Any]] = None,
    account_snapshots: Optional[Iterable[Any]] = None,
) -> ReplayReport:
    started_at = datetime.now().astimezone()
    results = adapter.replay(
        historical_bars,
        warmup_bars=warmup_bars,
        option_chain_snapshots=list(option_chain_snapshots or ()),
        account_snapshots=list(account_snapshots or ()),
    )
    bars = _bar_records(historical_bars)[warmup_bars:]
    observations = [
        observation_from_result(result) for result in results
    ]
    outcomes = calculate_outcomes(observations, bars, results)
    transitions = [
        ReplayTransitionRecord(
            timestamp=transition.timestamp,
            previous_state=transition.previous_state,
            new_state=transition.new_state,
            pipeline_version=transition.pipeline_version,
        )
        for transition in adapter.history
    ]
    return ReplayReport(
        symbol=adapter.symbol,
        timeframe=adapter.timeframe,
        started_at=started_at,
        completed_at=datetime.now().astimezone(),
        observations=observations,
        transitions=transitions,
        outcomes=outcomes,
        segments=segment_outcomes(outcomes),
    )


def observation_from_result(result: QXEvaluationResult) -> ReplayObservation:
    regime = result.market_regime
    direction = result.direction
    playbook = result.primary_playbook_candidate
    trigger = result.trigger
    tradeability = result.tradeability
    options = result.options_expression
    portfolio = result.portfolio_risk
    option_dependency = result.data_dependencies.get("option_chain")
    account_dependency = result.data_dependencies.get("account_snapshot")
    trigger_price = getattr(trigger, "trigger_price", None)
    invalidation_price = getattr(trigger, "invalidation_price", None)
    if trigger_price is None:
        trigger_price = getattr(playbook, "trigger_price", None)
    if invalidation_price is None:
        invalidation_price = getattr(playbook, "invalidation_price", None)
    coverage = getattr(direction, "direction_evidence_coverage", None)
    coverage_status = str(getattr(direction, "coverage_status", "UNAVAILABLE"))
    return ReplayObservation(
        symbol=result.symbol,
        timeframe=result.timeframe,
        timestamp=result.evaluation_timestamp,
        session_date=result.evaluation_timestamp.date().isoformat(),
        publication_state=_value(result.publication_state),
        trend_regime=_value(getattr(regime, "trend", "UNKNOWN")),
        volatility_regime=_value(getattr(regime, "volatility", "UNKNOWN")),
        gamma_regime=_value(getattr(regime, "gamma", "UNKNOWN")),
        session_regime=_value(getattr(regime, "session", "UNKNOWN")),
        direction_score=getattr(direction, "direction_score", None),
        direction_label=getattr(direction, "direction_label", None),
        direction_coverage=coverage,
        coverage_status=coverage_status,
        evidence_coverage_bucket=_coverage_bucket(coverage, coverage_status),
        playbook=getattr(playbook, "playbook_id", None),
        lifecycle_state=result.current_lifecycle_state,
        trigger_price=trigger_price,
        invalidation_price=invalidation_price,
        tradeability_state=_value(getattr(tradeability, "state", "UNAVAILABLE")),
        observed_entry_reference_price=getattr(
            tradeability, "observed_entry_reference_price", None
        ),
        options_state=_value(getattr(options, "state", "UNAVAILABLE")),
        portfolio_state=_value(getattr(portfolio, "state", "UNAVAILABLE")),
        option_snapshot_id=getattr(option_dependency, "snapshot_id", None),
        account_snapshot_id=getattr(account_dependency, "snapshot_id", None),
        option_snapshot_source=getattr(option_dependency, "source", "UNAVAILABLE"),
        account_snapshot_source=getattr(account_dependency, "source", "UNAVAILABLE"),
        market_driver_status=_value(getattr(getattr(result, "market_driver", None), "status", "UNAVAILABLE")),
        primary_driver=_value(getattr(getattr(getattr(result, "market_driver", None), "primary_driver", None), "driver_id", getattr(getattr(getattr(result, "market_driver", None), "primary_driver", None), "archetype", "UNAVAILABLE"))),
        driver_strength=_value(getattr(getattr(getattr(result, "market_driver", None), "primary_driver", None), "strength", "UNAVAILABLE")),
        driver_persistence_state=_value(getattr(getattr(getattr(getattr(result, "market_driver", None), "primary_driver", None), "persistence", getattr(getattr(result, "market_driver", None), "driver_persistence", None)), "state", "UNAVAILABLE")),
        driver_coverage_status=_value(getattr(getattr(getattr(result, "market_driver", None), "coverage", None), "status", getattr(getattr(getattr(result, "market_driver", None), "coverage", None), "coverage_status", "UNAVAILABLE"))),
        reason_codes=list(result.reason_codes),
        evidence_summary=list(result.evidence_summary),
        stage_latencies=dict(result.stage_latencies),
        engine_versions=dict(result.engine_versions),
        pipeline_version=result.pipeline_version,
    )


def calculate_outcomes(
    observations: list[ReplayObservation],
    bars: list[dict[str, Any]],
    results: list[QXEvaluationResult],
) -> list[ReplayOutcome]:
    if len(observations) != len(bars) or len(results) != len(bars):
        raise ValueError("Replay observations, results, and bars must align one-to-one")
    outcomes: list[ReplayOutcome] = []
    setup_index: Optional[int] = None
    armed_index: Optional[int] = None
    setup_identity: Optional[tuple[Any, ...]] = None
    processed_triggers: set[str] = set()

    for index, (observation, result) in enumerate(zip(observations, results)):
        identity = (
            observation.session_date,
            observation.playbook,
            observation.direction_label,
        )
        if observation.lifecycle_state in {LifecycleState.WATCH, LifecycleState.ARMED}:
            if setup_identity != identity:
                setup_index = index
                armed_index = None
                setup_identity = identity
            if observation.lifecycle_state == LifecycleState.ARMED and armed_index is None:
                armed_index = index
            if _invalidation_hit(
                bars[index],
                observation.direction_label or "UNKNOWN",
                observation.invalidation_price,
            ):
                outcomes.append(
                    _untriggered_outcome(
                        observations,
                        setup_index if setup_index is not None else index,
                        index,
                        armed_index=armed_index,
                        invalidated=True,
                    )
                )
                setup_index = None
                armed_index = None
                setup_identity = None
            continue

        trigger = result.trigger
        trigger_id = str(getattr(trigger, "playbook_evaluation_id", ""))
        if (
            trigger is not None
            and observation.lifecycle_state in TRIGGERED_STATES
            and trigger_id not in processed_triggers
        ):
            processed_triggers.add(trigger_id)
            setup_start = setup_index if setup_index is not None else index
            outcomes.append(
                _triggered_outcome(
                    observations,
                    bars,
                    results,
                    setup_start,
                    armed_index,
                    index,
                )
            )
            setup_index = None
            armed_index = None
            setup_identity = None
            continue

        if setup_index is not None and (
            observation.session_date != observations[setup_index].session_date
            or observation.lifecycle_state in {LifecycleState.NO_SETUP, LifecycleState.BLOCKED}
        ):
            outcomes.append(
                _untriggered_outcome(
                    observations,
                    setup_index,
                    max(index - 1, setup_index),
                    armed_index=armed_index,
                )
            )
            setup_index = None
            armed_index = None
            setup_identity = None

    if setup_index is not None:
        outcomes.append(
            _untriggered_outcome(
                observations,
                setup_index,
                len(observations) - 1,
                armed_index=armed_index,
            )
        )
    return outcomes


def _triggered_outcome(
    observations: list[ReplayObservation],
    bars: list[dict[str, Any]],
    results: list[QXEvaluationResult],
    setup_start: int,
    armed_index: Optional[int],
    trigger_index: int,
) -> ReplayOutcome:
    observation = observations[trigger_index]
    result = results[trigger_index]
    direction = observation.direction_label or getattr(result.trigger, "direction", "UNKNOWN")
    trigger_price = observation.trigger_price
    invalidation_price = observation.invalidation_price
    targets = list(getattr(result.tradeability, "target_candidates", ()) or ())
    target = _directional_target(targets, direction, trigger_price)
    trade_entry = None
    if observation.tradeability_state == "TRADEABLE":
        trade_entry = observation.observed_entry_reference_price
    tradeability_target = _directional_target(targets, direction, trade_entry)

    session_end = trigger_index
    while (
        session_end + 1 < len(observations)
        and observations[session_end + 1].session_date == observation.session_date
        and observations[session_end + 1].lifecycle_state in TRIGGERED_STATES
    ):
        session_end += 1
    next_index = session_end + 1
    ended_by_lifecycle = (
        next_index < len(observations)
        and observations[next_index].session_date == observation.session_date
    )
    open_outcome = (
        "OPEN_AT_LIFECYCLE_END" if ended_by_lifecycle else "OPEN_AT_SESSION_END"
    )

    trigger_event = getattr(result.trigger, "trigger_event", None)
    gap_confirmed = bool(getattr(trigger_event, "gap_beyond_trigger", False))
    measurement_start = trigger_index if gap_confirmed else trigger_index + 1

    signal = _measure_path(
        bars,
        measurement_start,
        session_end,
        direction,
        trigger_price,
        invalidation_price,
        target,
        open_outcome,
    )
    tradeability = (
        _measure_path(
            bars,
            measurement_start,
            signal["end_index"],
            direction,
            trade_entry,
            invalidation_price,
            tradeability_target,
            open_outcome,
        )
        if trade_entry is not None
        else None
    )
    end_index = int(signal["end_index"])
    outcome = str(signal["outcome"])
    false_trigger = bool(
        outcome == "INVALIDATED"
        and signal["mfe_r"] is not None
        and float(signal["mfe_r"]) < 1.0
    )
    if false_trigger:
        outcome = "FALSE_TRIGGER"
    armed_at = observations[armed_index].timestamp if armed_index is not None else None
    return ReplayOutcome(
        symbol=observation.symbol,
        timeframe=observation.timeframe,
        playbook=observation.playbook,
        direction=direction,
        setup_started_at=observations[setup_start].timestamp,
        armed_at=armed_at,
        triggered_at=observation.timestamp,
        ended_at=observations[end_index].timestamp,
        outcome=outcome,
        trigger_price=trigger_price,
        invalidation_price=invalidation_price,
        target_price=target,
        tradeability_target_price=tradeability_target,
        bars_to_trigger=(trigger_index - armed_index if armed_index is not None else None),
        seconds_to_trigger=(observation.timestamp - armed_at).total_seconds() if armed_at else None,
        bars_in_setup=end_index - setup_start + 1,
        seconds_in_setup=(observations[end_index].timestamp - observations[setup_start].timestamp).total_seconds(),
        false_trigger=false_trigger,
        ambiguous_same_bar=bool(signal["ambiguous"]),
        signal_risk=signal["risk"],
        signal_mfe=signal["mfe"],
        signal_mae=signal["mae"],
        signal_mfe_r=signal["mfe_r"],
        signal_mae_r=signal["mae_r"],
        signal_endpoint_r=signal["endpoint_r"],
        tradeability_entry_reference_price=trade_entry,
        tradeability_risk=tradeability["risk"] if tradeability else None,
        tradeability_mfe=tradeability["mfe"] if tradeability else None,
        tradeability_mae=tradeability["mae"] if tradeability else None,
        tradeability_mfe_r=tradeability["mfe_r"] if tradeability else None,
        tradeability_mae_r=tradeability["mae_r"] if tradeability else None,
        tradeability_endpoint_r=tradeability["endpoint_r"] if tradeability else None,
        trend_regime=observation.trend_regime,
        volatility_regime=observation.volatility_regime,
        session_regime=observation.session_regime,
        direction_label=observation.direction_label or "UNKNOWN",
        evidence_coverage_bucket=observation.evidence_coverage_bucket,
        primary_driver=observation.primary_driver,
    )


def _measure_path(
    bars: list[dict[str, Any]],
    start: int,
    stop: int,
    direction: str,
    entry: Optional[float],
    invalidation: Optional[float],
    target: Optional[float],
    open_outcome: str,
) -> dict[str, Any]:
    if entry is None or invalidation is None or entry == invalidation:
        return {
            "outcome": "UNMEASURABLE",
            "end_index": stop,
            "risk": None,
            "mfe": None,
            "mae": None,
            "mfe_r": None,
            "mae_r": None,
            "endpoint_r": None,
            "ambiguous": False,
        }
    bullish = _bullish(direction)
    risk = abs(entry - invalidation)
    mfe = 0.0
    mae = 0.0
    if start > stop:
        return {
            "outcome": open_outcome,
            "end_index": stop,
            "risk": risk,
            "mfe": 0.0,
            "mae": 0.0,
            "mfe_r": 0.0,
            "mae_r": 0.0,
            "endpoint_r": 0.0,
            "ambiguous": False,
        }
    endpoint_price = float(bars[stop].get("close", entry) or entry)
    outcome = open_outcome
    end_index = stop
    ambiguous = False
    for index in range(start, stop + 1):
        high = float(bars[index].get("high", entry) or entry)
        low = float(bars[index].get("low", entry) or entry)
        favorable = high - entry if bullish else entry - low
        adverse = entry - low if bullish else high - entry
        invalidated = low <= invalidation if bullish else high >= invalidation
        target_hit = False
        if target is not None:
            target_hit = high >= target if bullish else low <= target
        if invalidated and target_hit:
            mae = max(mae, risk)
            outcome = "INVALIDATED"
            endpoint_price = invalidation
            end_index = index
            ambiguous = True
            break
        if invalidated:
            mae = max(mae, risk)
            outcome = "INVALIDATED"
            endpoint_price = invalidation
            end_index = index
            break
        if target_hit:
            mfe = max(mfe, abs(target - entry))
            mae = max(mae, adverse)
            outcome = "TARGET_HIT"
            endpoint_price = target if target is not None else endpoint_price
            end_index = index
            break
        mfe = max(mfe, favorable)
        mae = max(mae, adverse)
    endpoint_move = endpoint_price - entry if bullish else entry - endpoint_price
    return {
        "outcome": outcome,
        "end_index": end_index,
        "risk": risk,
        "mfe": mfe,
        "mae": mae,
        "mfe_r": mfe / risk,
        "mae_r": mae / risk,
        "endpoint_r": endpoint_move / risk,
        "ambiguous": ambiguous,
    }


def _untriggered_outcome(
    observations: list[ReplayObservation],
    start: int,
    end: int,
    *,
    armed_index: Optional[int] = None,
    invalidated: bool = False,
) -> ReplayOutcome:
    observation = observations[start]
    return ReplayOutcome(
        symbol=observation.symbol,
        timeframe=observation.timeframe,
        playbook=observation.playbook,
        direction=observation.direction_label or "UNKNOWN",
        setup_started_at=observation.timestamp,
        armed_at=observations[armed_index].timestamp if armed_index is not None else None,
        ended_at=observations[end].timestamp,
        outcome="NO_TRIGGER",
        trigger_price=observation.trigger_price,
        invalidation_price=observation.invalidation_price,
        bars_in_setup=end - start + 1,
        seconds_in_setup=(observations[end].timestamp - observation.timestamp).total_seconds(),
        invalidation_before_trigger=invalidated,
        trend_regime=observation.trend_regime,
        volatility_regime=observation.volatility_regime,
        session_regime=observation.session_regime,
        direction_label=observation.direction_label or "UNKNOWN",
        evidence_coverage_bucket=observation.evidence_coverage_bucket,
        primary_driver=observation.primary_driver,
    )


def segment_outcomes(outcomes: list[ReplayOutcome]) -> list[ReplaySegmentSummary]:
    dimensions = {
        "playbook": lambda item: item.playbook or "UNAVAILABLE",
        "market_regime": lambda item: item.trend_regime,
        "direction": lambda item: item.direction_label,
        "evidence_coverage": lambda item: item.evidence_coverage_bucket,
        "session_regime": lambda item: item.session_regime,
        "volatility_regime": lambda item: item.volatility_regime,
    }
    summaries: list[ReplaySegmentSummary] = []
    for segment, getter in dimensions.items():
        grouped: dict[str, list[ReplayOutcome]] = {}
        for outcome in outcomes:
            grouped.setdefault(str(getter(outcome)), []).append(outcome)
        for value, items in sorted(grouped.items()):
            triggered = [item for item in items if item.triggered_at is not None]
            summaries.append(
                ReplaySegmentSummary(
                    segment=segment,
                    value=value,
                    setups=len(items),
                    triggered=len(triggered),
                    false_trigger_rate=(
                        sum(item.false_trigger for item in triggered) / len(triggered)
                        if triggered
                        else None
                    ),
                    invalidation_before_trigger_rate=(
                        sum(item.invalidation_before_trigger for item in items) / len(items)
                        if items
                        else None
                    ),
                    average_signal_mfe_r=_average(item.signal_mfe_r for item in triggered),
                    average_signal_mae_r=_average(item.signal_mae_r for item in triggered),
                    average_signal_endpoint_r=_average(
                        item.signal_endpoint_r for item in triggered
                    ),
                    average_tradeability_mfe_r=_average(
                        item.tradeability_mfe_r for item in triggered
                    ),
                    average_tradeability_mae_r=_average(
                        item.tradeability_mae_r for item in triggered
                    ),
                    average_tradeability_endpoint_r=_average(
                        item.tradeability_endpoint_r for item in triggered
                    ),
                )
            )
    return summaries


def _bar_records(bars: Any) -> list[dict[str, Any]]:
    if isinstance(bars, pd.DataFrame):
        records: list[dict[str, Any]] = []
        for _, row in bars.iterrows():
            record = row.to_dict()
            timestamp = bar_timestamp(row)
            if timestamp is not None:
                record["timestamp"] = timestamp
            records.append(record)
        return records
    return [dict(bar) if isinstance(bar, dict) else vars(bar) for bar in bars]


def _directional_target(
    targets: list[float], direction: str, entry: Optional[float]
) -> Optional[float]:
    if entry is None:
        return None
    candidates = [float(target) for target in targets]
    if _bullish(direction):
        valid = [target for target in candidates if target > entry]
        return min(valid) if valid else None
    valid = [target for target in candidates if target < entry]
    return max(valid) if valid else None


def _invalidation_hit(
    bar: dict[str, Any], direction: str, invalidation: Optional[float]
) -> bool:
    if invalidation is None:
        return False
    return (
        float(bar.get("low", invalidation) or invalidation) <= invalidation
        if _bullish(direction)
        else float(bar.get("high", invalidation) or invalidation) >= invalidation
    )


def _bullish(direction: str) -> bool:
    return "BULL" in direction.upper() or direction.upper() in {"LONG", "UP"}


def _coverage_bucket(value: Optional[float], status: str) -> str:
    if status and status != "UNAVAILABLE":
        return status
    if value is None:
        return "UNAVAILABLE"
    if value < 0.25:
        return "INSUFFICIENT"
    if value < 0.50:
        return "PARTIAL"
    if value < 0.75:
        return "ADEQUATE"
    if value < 1.0:
        return "STRONG"
    return "COMPLETE"


def _average(values: Iterable[Optional[float]]) -> Optional[float]:
    available = [float(value) for value in values if value is not None]
    return fmean(available) if available else None


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))
