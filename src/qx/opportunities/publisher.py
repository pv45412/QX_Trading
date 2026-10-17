from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from qx.opportunities.identity import (
    command_identity,
    command_payload_hash,
    json_value,
    new_evaluation_id,
    sha256_digest,
    stream_key,
    utc_timestamp,
)
from qx.opportunities.models import ObservationMode, OpportunityRecord
from qx.opportunities.repository import CommandReservation, OpportunityRepository
from qx.pipeline.models import QXEvaluationContext, QXEvaluationResult
from qx.pipeline.point_in_time import evaluated_bar_window_sha256, filter_bars_at_or_before


STRUCTURE_FIELDS = (
    "regime", "latest_bos", "latest_choch", "latest_event", "events",
    "confirmed_pivots", "protected_low", "protected_high", "active_high", "active_low",
    "demand_ob", "supply_ob", "order_blocks", "liquidity_pools", "structure_score",
)
REGIME_FIELDS = (
    "trend", "volatility", "gamma", "session", "trend_evidence", "volatility_evidence",
    "gamma_evidence", "session_evidence", "regime_generated_at", "data_as_of",
    "config_version", "engine_version",
)
DIRECTION_FIELDS = (
    "symbol", "timeframe", "direction_score", "direction_label",
    "direction_evidence_coverage", "coverage_status", "trade_state", "factors",
    "total_effective_weight", "total_configured_weight", "config_version", "engine_version",
    "event_timestamp", "knowledge_timestamp",
)
PLAYBOOK_FIELDS = (
    "playbook_id", "playbook_version", "symbol", "timeframe", "direction", "state",
    "setup_detected", "reason_code", "setup_quality_components", "trigger_definition",
    "trigger_price", "trigger_source_type", "trigger_source_id", "trigger_knowledge_timestamp",
    "invalidation_price", "invalidation_source_type", "invalidation_source_id",
    "invalidation_knowledge_timestamp", "structural_target_candidates", "publication_state",
    "direction_score", "direction_evidence_coverage", "market_regime",
    "source_structure_event_ids", "source_order_block_ids", "source_pivot_ids", "rule_results",
    "event_timestamp", "knowledge_timestamp", "config_version", "engine_version", "trade_state",
)
TRIGGER_FIELDS = (
    "playbook_evaluation_id", "playbook_id", "symbol", "timeframe", "direction", "state",
    "trigger_event", "armed_at", "trigger_level_known_at", "trigger_event_timestamp",
    "trigger_confirmed_at", "trigger_price", "invalidation_price", "publication_state",
    "structure_valid", "trigger_source_valid", "evidence_ladder", "config_version",
    "engine_version", "trade_state",
)
TRADEABILITY_FIELDS = (
    "tradeability_id", "triggered_setup_id", "playbook_id", "symbol", "timeframe",
    "direction", "state", "publication_state", "trigger_price", "observed_underlying_price",
    "observed_entry_reference_price", "invalidation_price", "target_candidates",
    "participation_score", "participation_evidence_coverage", "rvol_normalized",
    "rvol_percentile", "delta_score", "delta_level", "delta_directional_alignment",
    "delta_change", "delta_slope", "delta_provenance", "delta_reliability", "extension_atr",
    "liquidity_applicability", "spread_absolute", "spread_pct", "liquidity_status",
    "risk_reward_to_target1", "risk_reward_to_best_structural_target", "gap_beyond_trigger",
    "gap_distance_atr", "bars_since_trigger", "seconds_since_trigger", "triggered_at",
    "tradeability_evaluated_at", "evaluated_at", "data_as_of", "reason_codes",
    "evidence_ladder", "config_version", "engine_version", "trade_state",
)
OPTIONS_FIELDS = (
    "expression_id", "tradeability_id", "playbook_id", "symbol", "direction", "state",
    "trade_state", "underlying_price", "data_as_of", "evaluated_at", "publication_state",
    "iv", "iv_rank", "iv_percentile", "volatility_regime", "event_risk",
    "candidate_strategies", "primary_candidate_id", "structural_target_id",
    "structural_target_price", "short_strike", "target_fit_distance", "target_fit_score",
    "event_risk_identified", "events", "event_policy", "event_penalty_applied", "reason_codes",
    "evidence_ladder", "config_version", "engine_version",
)
PORTFOLIO_FIELDS = (
    "risk_result_id", "expression_id", "candidate_id", "symbol", "strategy_type", "direction",
    "state", "trade_state", "recommended_max_contracts", "approved_contracts_cap",
    "binding_constraint", "exposure_basis", "reason_codes", "evaluated_at", "data_as_of",
    "config_version", "engine_version",
)
DEPENDENCY_FIELDS = (
    "name", "available", "source", "data_as_of", "freshness", "publication_state",
    "sync_status", "reason_code", "cache_status", "snapshot_id", "quality_status",
    "quality_reason_codes", "requested_timeframe", "observed_timeframe", "bar_count",
    "usable_bar_count", "incomplete_candle_count", "retrieved_at", "content_sha256",
)


class OpportunityPublicationError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpportunityPublicationPlan:
    reservation: CommandReservation
    existing_record: OpportunityRecord | None = None

    @property
    def should_execute(self) -> bool:
        return self.reservation.should_execute


class OpportunityPublisher:
    def __init__(self, repository: OpportunityRepository, *, environment_id: str) -> None:
        self.repository = repository
        self.environment_id = environment_id

    def reserve_publication(
        self,
        *,
        producer_id: str,
        producer_run_id: str,
        symbol: str,
        timeframe: str,
    ) -> OpportunityPublicationPlan:
        identity_values = {
            "environment_id": self.environment_id,
            "producer_id": producer_id,
            "producer_run_id": producer_run_id,
            "symbol": symbol,
            "timeframe": timeframe,
        }
        payload_hash = command_payload_hash(**identity_values)
        idempotency_key = command_identity(**identity_values)
        reservation = self.repository.reserve_command(
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            producer_id=producer_id,
            producer_run_id=producer_run_id,
        )
        if not reservation.should_execute:
            record = self.repository.get_record(
                reservation.evaluation_id or "",
                environment_id=self.environment_id,
            )
            if record is None:
                raise OpportunityPublicationError("Committed command result is unavailable")
            return OpportunityPublicationPlan(reservation=reservation, existing_record=record)
        return OpportunityPublicationPlan(reservation=reservation)

    def publish_reserved(
        self,
        *,
        plan: OpportunityPublicationPlan,
        result: QXEvaluationResult,
        context: QXEvaluationContext,
        producer_id: str,
        producer_run_id: str,
        expires_at: datetime,
        freshness_policy_version: str,
        horizon_context: str | None = None,
    ) -> OpportunityRecord:
        if not plan.should_execute:
            if plan.existing_record is None:
                raise OpportunityPublicationError("Committed command result is unavailable")
            return plan.existing_record
        expected_key = command_identity(
            environment_id=self.environment_id,
            producer_id=producer_id,
            producer_run_id=producer_run_id,
            symbol=context.symbol,
            timeframe=context.timeframe,
        )
        if plan.reservation.idempotency_key != expected_key:
            raise OpportunityPublicationError("Reserved command does not match publication input")
        if (
            result.symbol.upper() != context.symbol.upper()
            or result.timeframe.lower() != context.timeframe.lower()
            or result.evaluation_timestamp != context.evaluation_timestamp
        ):
            raise OpportunityPublicationError("Pipeline result does not match evaluation context")
        bar_source_sha256, bar_retrieved_at = _validate_publication_inputs(
            context,
            expires_at,
        )
        record = build_opportunity_record(
            result=result,
            context=context,
            reservation=plan.reservation,
            environment_id=self.environment_id,
            producer_id=producer_id,
            producer_run_id=producer_run_id,
            expires_at=expires_at,
            freshness_policy_version=freshness_policy_version,
            bar_source_sha256=bar_source_sha256,
            bar_retrieved_at=bar_retrieved_at,
            horizon_context=horizon_context,
        )
        return self.repository.commit_record(record)

    def abandon_reserved(
        self,
        plan: OpportunityPublicationPlan,
        *,
        failure_code: str,
    ) -> bool:
        if not plan.should_execute:
            return False
        return self.repository.abandon_command(
            plan.reservation.idempotency_key,
            failure_code=failure_code,
        )

def build_opportunity_record(
    *,
    result: QXEvaluationResult,
    context: QXEvaluationContext,
    reservation: CommandReservation,
    environment_id: str,
    producer_id: str,
    producer_run_id: str,
    expires_at: datetime,
    freshness_policy_version: str,
    bar_source_sha256: str,
    bar_retrieved_at: datetime,
    horizon_context: str | None,
) -> OpportunityRecord:
    horizon_context = horizon_context or getattr(result, "horizon", None) or getattr(context, "horizon", None)
    recorded_at = datetime.now(timezone.utc)
    decision = safe_decision_projection(result)
    visible_bars = filter_bars_at_or_before(context.bars, result.evaluation_timestamp)
    try:
        bar_window_sha256 = evaluated_bar_window_sha256(visible_bars, result.timeframe)
    except ValueError as exc:
        raise OpportunityPublicationError("Canonical evaluated bar window is required") from exc
    if result.evaluated_bar_window_sha256 != bar_window_sha256:
        raise OpportunityPublicationError("Canonical evaluated bar-window digest mismatch")
    bar_count = len(visible_bars)
    first_bar_timestamp = visible_bars.iloc[0]["timestamp"].to_pydatetime()
    last_bar_timestamp = visible_bars.iloc[-1]["timestamp"].to_pydatetime()
    dependencies = {
        name: dependency.model_dump(mode="json")
        for name, dependency in result.data_dependencies.items()
    }
    input_fingerprint = sha256_digest(
        {
            "schema_version": "qx.opportunity-input.v1",
            "environment_id": environment_id,
            "producer_id": producer_id,
            "symbol": result.symbol.upper(),
            "timeframe": result.timeframe.lower(),
            "evaluation_timestamp": result.evaluation_timestamp,
            "bar_window_sha256": bar_window_sha256,
            "bar_count": bar_count,
            "first_bar_timestamp": first_bar_timestamp,
            "last_bar_timestamp": last_bar_timestamp,
            "bar_source_sha256": bar_source_sha256,
            "bar_retrieved_at": bar_retrieved_at,
            "data_dependencies": dependencies,
            "pipeline_version": result.pipeline_version,
            "config_version": result.config_version,
            "engine_versions": result.engine_versions,
        }
    )
    direction = None
    evidence_coverage = None
    coverage_status = None
    if result.direction is not None:
        direction = _value(result.direction.direction_label)
        evidence_coverage = result.direction.direction_evidence_coverage
        coverage_status = _value(result.direction.coverage_status)
    playbook_id = (
        result.primary_playbook_candidate.playbook_id
        if result.primary_playbook_candidate is not None
        else None
    )
    setup_reference = result.trigger.playbook_evaluation_id if result.trigger is not None else None
    return OpportunityRecord(
        evaluation_id=new_evaluation_id(recorded_at),
        idempotency_key=reservation.idempotency_key,
        environment_id=environment_id,
        producer_id=producer_id,
        producer_run_id=producer_run_id,
        symbol=result.symbol.upper(),
        timeframe=result.timeframe.lower(),
        horizon_context=horizon_context,
        evaluation_timestamp=result.evaluation_timestamp,
        request_started_at=result.request_started_at,
        recorded_at=recorded_at,
        expires_at=expires_at,
        freshness_policy_version=freshness_policy_version,
        publication_state=_value(result.publication_state),
        lifecycle_state=result.current_lifecycle_state,
        pipeline_version=result.pipeline_version,
        config_version=result.config_version,
        engine_versions=result.engine_versions,
        direction=direction,
        primary_playbook_id=playbook_id,
        source_setup_reference=setup_reference,
        reason_codes=result.reason_codes,
        evidence_coverage=evidence_coverage,
        coverage_status=coverage_status,
        data_dependencies=dependencies,
        market_driver=decision.get("market_driver"),
        decision_payload=decision,
        input_fingerprint=input_fingerprint,
        bar_window_sha256=bar_window_sha256,
        result_sha256=sha256_digest(
            {"schema_version": "qx.opportunity-decision.v1", "decision": decision}
        ),
        stream_key=stream_key(
            environment_id=environment_id,
            observation_mode=ObservationMode.LIVE.value,
            symbol=result.symbol,
            timeframe=result.timeframe,
            pipeline_version=result.pipeline_version,
            config_version=result.config_version,
        ),
    )


def safe_decision_projection(result: QXEvaluationResult) -> dict[str, Any]:
    payload = {
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "evaluation_timestamp": result.evaluation_timestamp,
        "request_started_at": result.request_started_at,
        "publication_state": result.publication_state,
        "structure": _project_model(result.structure, STRUCTURE_FIELDS),
        "market_regime": _project_model(result.market_regime, REGIME_FIELDS),
        "direction": _project_model(result.direction, DIRECTION_FIELDS),
        "playbooks": [
            _project_model(playbook, PLAYBOOK_FIELDS) for playbook in result.playbooks or []
        ] if result.playbooks is not None else None,
        "primary_playbook_candidate": _project_model(
            result.primary_playbook_candidate,
            PLAYBOOK_FIELDS,
        ),
        "trigger": _project_model(result.trigger, TRIGGER_FIELDS),
        "tradeability": _project_model(result.tradeability, TRADEABILITY_FIELDS),
        "options_expression": _project_model(result.options_expression, OPTIONS_FIELDS),
        "portfolio_risk": _project_model(result.portfolio_risk, PORTFOLIO_FIELDS),
        "market_driver": (
            result.market_driver.to_presentation_dict()
            if getattr(result, "market_driver", None) is not None
            else None
        ),
        "current_lifecycle_state": result.current_lifecycle_state,
        "evidence_summary": list(result.evidence_summary),
        "reason_codes": list(result.reason_codes),
        "config_version": result.config_version,
        "pipeline_version": result.pipeline_version,
        "engine_versions": dict(result.engine_versions),
        "stage_latencies": dict(result.stage_latencies),
        "data_dependencies": {
            name: _project_model(dependency, DEPENDENCY_FIELDS)
            for name, dependency in result.data_dependencies.items()
        },
    }
    return json_value(payload)


def _project_model(value: Any, fields: tuple[str, ...]) -> dict[str, Any] | None:
    if value is None:
        return None
    source = value.model_dump(mode="python") if hasattr(value, "model_dump") else dict(value)
    return {field: json_value(source[field]) for field in fields if field in source}


def _validate_publication_inputs(
    context: QXEvaluationContext,
    expires_at: datetime,
) -> tuple[str, datetime]:
    if context.evaluation_timestamp.tzinfo is None:
        raise OpportunityPublicationError("Evaluation timestamp must be timezone-aware")
    if expires_at.tzinfo is None or expires_at <= context.evaluation_timestamp:
        raise OpportunityPublicationError("Approved expires_at must follow evaluation timestamp")
    bars_dependency = context.data_dependencies.get("bars")
    if bars_dependency is None:
        raise OpportunityPublicationError("Validated bar dependency is required")
    bar_source_sha256 = bars_dependency.content_sha256 or ""
    bar_retrieved_at = bars_dependency.retrieved_at
    if len(bar_source_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in bar_source_sha256
    ):
        raise OpportunityPublicationError("Validated bar source SHA-256 is required")
    if bar_retrieved_at is None or bar_retrieved_at.tzinfo is None:
        raise OpportunityPublicationError("Validated bar retrieval timestamp is required")
    if bar_retrieved_at > context.evaluation_timestamp:
        raise OpportunityPublicationError("Bar retrieval must be visible by evaluation time")
    return bar_source_sha256, bar_retrieved_at


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))
