from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qx.interfaces.opportunities import create_opportunity_router
from qx.opportunities.identity import (
    command_identity,
    command_payload_hash,
    new_evaluation_id,
    sha256_digest,
    stream_key,
)
from qx.opportunities.migrations import (
    MIGRATION_000,
    MIGRATION_000_SQL,
    MIGRATION_001,
    OpportunityMigrationError,
    apply_opportunity_migrations,
)
from qx.opportunities.models import OpportunityRecord, PublicationCommandState
from qx.opportunities.publisher import (
    OpportunityPublisher,
    safe_decision_projection,
)
from qx.opportunities.repository import (
    IdempotencyConflict,
    OpportunityRepository,
    OpportunityRepositoryError,
    ReservationInProgress,
)
from qx.models.rules import PublicationState
from qx.pipeline.models import (
    DataDependencyStatus,
    LifecycleState,
    QXEvaluationContext,
    QXEvaluationResult,
)
from qx.pipeline.point_in_time import evaluated_bar_window_sha256, filter_bars_at_or_before
from qx.config.rules_config import load_rules_config
from qx.portfolio.models import PortfolioRiskResult, PortfolioRiskState


UTC = timezone.utc
BASE_TIME = datetime(2026, 9, 16, 14, 30, tzinfo=UTC)


def _repository(tmp_path) -> OpportunityRepository:
    return OpportunityRepository(tmp_path / "runtime.db", reconciliation_ttl=timedelta(minutes=5))


def _reserve(
    repository: OpportunityRepository,
    key: str,
    *,
    payload_hash: str = "a" * 64,
    now: datetime = BASE_TIME,
):
    return repository.reserve_command(
        idempotency_key=key,
        payload_hash=payload_hash,
        producer_id="canonical_live_publisher",
        producer_run_id=f"run-{key}",
        now=now,
    )


def _record(
    repository: OpportunityRepository,
    number: int,
    *,
    state: LifecycleState,
    evaluated_at: datetime,
    recorded_at: datetime | None = None,
    expires_at: datetime | None = None,
    symbol: str = "SPY",
    timeframe: str = "5m",
    publication_state: str = "RESEARCH_ONLY",
    direction: str | None = "BEARISH",
) -> OpportunityRecord:
    producer_id = "canonical_live_publisher"
    producer_run_id = f"run-{number}"
    identity_values = {
        "environment_id": "local",
        "producer_id": producer_id,
        "producer_run_id": producer_run_id,
        "symbol": symbol,
        "timeframe": timeframe,
    }
    key = command_identity(**identity_values)
    repository.reserve_command(
        idempotency_key=key,
        payload_hash=command_payload_hash(**identity_values),
        producer_id=producer_id,
        producer_run_id=producer_run_id,
        now=evaluated_at - timedelta(seconds=1),
    )
    evaluation_id = f"qxev1_{number:032x}"
    request_started_at = evaluated_at - timedelta(seconds=2)
    dependencies = {
        "bars": {
            "data_as_of": evaluated_at.isoformat(),
            "retrieved_at": (evaluated_at - timedelta(seconds=1)).isoformat(),
            "content_sha256": "c" * 64,
        }
    }
    reasons = [f"STATE_{state.value}"]
    decision = {
        "symbol": symbol,
        "timeframe": timeframe,
        "evaluation_timestamp": evaluated_at.isoformat(),
        "request_started_at": request_started_at.isoformat(),
        "publication_state": publication_state,
        "current_lifecycle_state": state.value,
        "evidence_summary": [],
        "reason_codes": reasons,
        "config_version": "research_v1",
        "pipeline_version": "core_v1",
        "engine_versions": {},
        "stage_latencies": {},
        "data_dependencies": dependencies,
        "nullable": None,
        "zero": 0,
        "false": False,
        "empty": "",
    }
    record = OpportunityRecord(
        evaluation_id=evaluation_id,
        idempotency_key=key,
        environment_id="local",
        producer_id=producer_id,
        producer_run_id=producer_run_id,
        symbol=symbol,
        timeframe=timeframe,
        evaluation_timestamp=evaluated_at,
        request_started_at=request_started_at,
        recorded_at=recorded_at or evaluated_at + timedelta(seconds=1),
        expires_at=expires_at or evaluated_at + timedelta(hours=1),
        freshness_policy_version="test_policy_v1",
        publication_state=publication_state,
        lifecycle_state=state,
        pipeline_version="core_v1",
        config_version="research_v1",
        direction=direction,
        primary_playbook_id="ORB",
        reason_codes=reasons,
        evidence_coverage=0.75,
        coverage_status="SUFFICIENT",
        data_dependencies=dependencies,
        decision_payload=decision,
        input_fingerprint=sha256_digest({"input": number}),
        bar_window_sha256=sha256_digest({"bars": number}),
        result_sha256=sha256_digest(
            {"schema_version": "qx.opportunity-decision.v1", "decision": decision}
        ),
        stream_key=stream_key(
            environment_id="local",
            observation_mode="LIVE",
            symbol=symbol,
            timeframe=timeframe,
            pipeline_version="core_v1",
            config_version="research_v1",
        ),
    )
    return repository.commit_record(record)


def test_migration_zero_uses_strict_create_table() -> None:
    assert "CREATE TABLE qx_schema_migrations" in MIGRATION_000_SQL
    assert "IF NOT EXISTS" not in MIGRATION_000_SQL


def test_clean_install_and_already_applied_migrations_are_idempotent(tmp_path) -> None:
    database = tmp_path / "runtime.db"
    apply_opportunity_migrations(str(database))
    apply_opportunity_migrations(str(database))
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """SELECT migration_id, migration_checksum
               FROM qx_schema_migrations ORDER BY migration_id"""
        ).fetchall()
    assert rows == [
        (MIGRATION_000.migration_id, MIGRATION_000.checksum),
        (MIGRATION_001.migration_id, MIGRATION_001.checksum),
    ]


def test_migration_checksum_mismatch_fails_closed(tmp_path) -> None:
    database = tmp_path / "runtime.db"
    apply_opportunity_migrations(str(database))
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE qx_schema_migrations SET migration_checksum = 'wrong' WHERE migration_id = ?",
            (MIGRATION_001.migration_id,),
        )
    with pytest.raises(OpportunityMigrationError, match="checksum mismatch"):
        apply_opportunity_migrations(str(database))


def test_unledgered_schema_drift_fails_closed(tmp_path) -> None:
    database = tmp_path / "runtime.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE opportunity_evaluations (evaluation_id TEXT PRIMARY KEY)")
    with pytest.raises(OpportunityMigrationError, match="Unledgered"):
        apply_opportunity_migrations(str(database))


def test_ledger_without_migration_zero_proof_fails_closed(tmp_path) -> None:
    database = tmp_path / "runtime.db"
    with sqlite3.connect(database) as connection:
        connection.execute(MIGRATION_000_SQL)
    with pytest.raises(OpportunityMigrationError, match="does not prove"):
        apply_opportunity_migrations(str(database))


def test_command_payload_hash_is_stable_and_scoped() -> None:
    first = command_payload_hash(
        environment_id="local",
        producer_id="publisher",
        producer_run_id="run-1",
        symbol="spy",
        timeframe="5M",
    )
    second = command_payload_hash(
        environment_id="local",
        producer_id="publisher",
        producer_run_id="run-1",
        symbol="SPY",
        timeframe="5m",
    )
    assert first == second
    assert first != command_payload_hash(
        environment_id="prod",
        producer_id="publisher",
        producer_run_id="run-1",
        symbol="SPY",
        timeframe="5m",
    )


def test_uuid7_evaluation_identity_has_version_and_prefix() -> None:
    evaluation_id = new_evaluation_id(BASE_TIME)
    assert evaluation_id.startswith("qxev1_")
    assert len(evaluation_id) == 38
    assert evaluation_id[18] == "7"


def test_reserved_command_rejects_concurrent_duplicate(tmp_path) -> None:
    repository = _repository(tmp_path)
    _reserve(repository, "same")
    with pytest.raises(ReservationInProgress):
        _reserve(repository, "same", now=BASE_TIME + timedelta(minutes=1))


def test_reserved_command_becomes_abandoned_without_creating_record(tmp_path) -> None:
    repository = _repository(tmp_path)
    _reserve(repository, "crashed")
    changed = repository.reconcile_abandoned(now=BASE_TIME + timedelta(minutes=6))
    assert changed == 1
    assert repository.get_detail("qxev1_" + "0" * 32, environment_id="local") is None
    reservation = _reserve(repository, "crashed", now=BASE_TIME + timedelta(minutes=7))
    assert reservation.state is PublicationCommandState.RESERVED
    assert reservation.should_execute is True
    assert reservation.attempt_count == 2


def test_same_key_with_different_payload_hash_conflicts(tmp_path) -> None:
    repository = _repository(tmp_path)
    _reserve(repository, "same", payload_hash="a" * 64)
    with pytest.raises(IdempotencyConflict):
        _reserve(repository, "same", payload_hash="b" * 64)


def test_committed_command_returns_prior_identity_and_prevents_duplicate(tmp_path) -> None:
    repository = _repository(tmp_path)
    record = _record(repository, 1, state=LifecycleState.ARMED, evaluated_at=BASE_TIME)
    identity_values = {
        "environment_id": record.environment_id,
        "producer_id": record.producer_id,
        "producer_run_id": record.producer_run_id,
        "symbol": record.symbol,
        "timeframe": record.timeframe,
    }
    reservation = repository.reserve_command(
        idempotency_key=record.idempotency_key,
        payload_hash=command_payload_hash(**identity_values),
        producer_id=record.producer_id,
        producer_run_id=record.producer_run_id,
        now=BASE_TIME + timedelta(minutes=1),
    )
    assert reservation.should_execute is False
    assert reservation.evaluation_id == record.evaluation_id
    with pytest.raises(OpportunityRepositoryError):
        repository.commit_record(record.model_copy(update={"evaluation_id": f"qxev1_{2:032x}"}))


def test_latest_state_filter_cannot_resurrect_older_armed_record(tmp_path) -> None:
    repository = _repository(tmp_path)
    _record(repository, 1, state=LifecycleState.ARMED, evaluated_at=BASE_TIME)
    _record(
        repository,
        2,
        state=LifecycleState.NO_SETUP,
        evaluated_at=BASE_TIME + timedelta(minutes=5),
    )
    result = repository.list_latest(
        environment_id="local",
        query_as_of=BASE_TIME + timedelta(minutes=10),
        states=[LifecycleState.ARMED.value],
    )
    assert result.items == []


def test_latest_blocked_state_cannot_resurrect_older_triggered_record(tmp_path) -> None:
    repository = _repository(tmp_path)
    _record(repository, 1, state=LifecycleState.TRIGGERED, evaluated_at=BASE_TIME)
    _record(
        repository,
        2,
        state=LifecycleState.BLOCKED,
        evaluated_at=BASE_TIME + timedelta(minutes=5),
        publication_state="BLOCKED",
    )
    result = repository.list_latest(
        environment_id="local",
        query_as_of=BASE_TIME + timedelta(minutes=10),
        states=[LifecycleState.TRIGGERED.value],
    )
    assert result.items == []


def test_include_blocked_returns_latest_blocked_stream_head(tmp_path) -> None:
    repository = _repository(tmp_path)
    _record(repository, 1, state=LifecycleState.TRIGGERED, evaluated_at=BASE_TIME)
    blocked = _record(
        repository,
        2,
        state=LifecycleState.BLOCKED,
        evaluated_at=BASE_TIME + timedelta(minutes=5),
        publication_state="BLOCKED",
    )
    result = repository.list_latest(
        environment_id="local",
        query_as_of=BASE_TIME + timedelta(minutes=10),
        include_blocked=True,
    )
    assert [item.evaluation_id for item in result.items] == [blocked.evaluation_id]


def test_point_in_time_boundaries_exclude_future_evaluation_and_knowledge(tmp_path) -> None:
    repository = _repository(tmp_path)
    _record(
        repository,
        1,
        state=LifecycleState.ARMED,
        evaluated_at=BASE_TIME + timedelta(minutes=5),
    )
    _record(
        repository,
        2,
        state=LifecycleState.ARMED,
        evaluated_at=BASE_TIME - timedelta(minutes=5),
        recorded_at=BASE_TIME + timedelta(minutes=5),
    )
    result = repository.list_latest(
        environment_id="local",
        query_as_of=BASE_TIME,
        knowledge_as_of=BASE_TIME,
    )
    assert result.items == []


def test_expired_record_is_excluded_from_current_list_but_available_by_identity(tmp_path) -> None:
    repository = _repository(tmp_path)
    record = _record(
        repository,
        1,
        state=LifecycleState.ARMED,
        evaluated_at=BASE_TIME,
        expires_at=BASE_TIME + timedelta(minutes=2),
    )
    result = repository.list_latest(
        environment_id="local",
        query_as_of=BASE_TIME + timedelta(minutes=3),
    )
    assert result.items == []
    assert repository.get_detail(record.evaluation_id, environment_id="local") is not None


def test_detail_preserves_null_zero_false_and_empty_string(tmp_path) -> None:
    repository = _repository(tmp_path)
    record = _record(repository, 1, state=LifecycleState.ARMED, evaluated_at=BASE_TIME)
    detail = repository.get_detail(record.evaluation_id, environment_id="local")
    assert detail is not None
    assert detail.decision["nullable"] is None
    assert detail.decision["zero"] == 0
    assert detail.decision["false"] is False
    assert detail.decision["empty"] == ""


def test_detail_identity_is_scoped_to_environment(tmp_path) -> None:
    repository = _repository(tmp_path)
    record = _record(repository, 1, state=LifecycleState.ARMED, evaluated_at=BASE_TIME)
    assert repository.get_detail(record.evaluation_id, environment_id="local") is not None
    assert repository.get_detail(record.evaluation_id, environment_id="production") is None


def test_safe_projection_removes_account_sensitive_portfolio_fields() -> None:
    result = QXEvaluationResult.model_construct(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=BASE_TIME,
        request_started_at=BASE_TIME,
        publication_state=PublicationState.RESEARCH_ONLY,
        structure=None,
        market_regime=None,
        direction=None,
        playbooks=None,
        primary_playbook_candidate=None,
        trigger=None,
        tradeability=None,
        options_expression=None,
        portfolio_risk=PortfolioRiskResult.model_construct(
            state=PortfolioRiskState.PORTFOLIO_APPROVED,
            account_id="secret-account",
            account_equity=100000,
            buying_power_available=50000,
            approved_contracts_cap=1,
            reason_codes=[],
        ),
        current_lifecycle_state=LifecycleState.PORTFOLIO_APPROVED,
        evidence_summary=[],
        reason_codes=[],
        config_version="research_v1",
        pipeline_version="core_v1",
        engine_versions={},
        stage_latencies={},
        data_dependencies={},
        io_metrics=[],
    )
    projected = safe_decision_projection(result)
    portfolio = projected["portfolio_risk"]
    assert portfolio["approved_contracts_cap"] == 1
    assert "account_id" not in portfolio
    assert "account_equity" not in portfolio
    assert "buying_power_available" not in portfolio
    object.__setattr__(result, "future_sensitive_field", "must-not-persist")
    assert "future_sensitive_field" not in safe_decision_projection(result)


def test_repository_rejects_sensitive_payload_even_if_publisher_is_bypassed(tmp_path) -> None:
    repository = _repository(tmp_path)
    record = _record(repository, 1, state=LifecycleState.ARMED, evaluated_at=BASE_TIME)
    producer_run_id = "run-sensitive"
    identity_values = {
        "environment_id": "local",
        "producer_id": "canonical_live_publisher",
        "producer_run_id": producer_run_id,
        "symbol": record.symbol,
        "timeframe": record.timeframe,
    }
    sensitive_key = command_identity(**identity_values)
    repository.reserve_command(
        idempotency_key=sensitive_key,
        payload_hash=command_payload_hash(**identity_values),
        producer_id="canonical_live_publisher",
        producer_run_id=producer_run_id,
        now=BASE_TIME,
    )
    unsafe_decision = {**record.decision_payload, "account_id": "must-not-persist"}
    unsafe = record.model_copy(
        update={
            "evaluation_id": f"qxev1_{2:032x}",
            "idempotency_key": sensitive_key,
            "producer_run_id": producer_run_id,
            "decision_payload": unsafe_decision,
            "result_sha256": sha256_digest(
                {"schema_version": "qx.opportunity-decision.v1", "decision": unsafe_decision}
            ),
        }
    )
    with pytest.raises(OpportunityRepositoryError, match="Sensitive opportunity field"):
        repository.commit_record(unsafe)


def test_publisher_reserves_before_acquisition_and_publishes_completed_result(tmp_path) -> None:
    repository = _repository(tmp_path)
    publisher = OpportunityPublisher(repository, environment_id="local")
    plan = publisher.reserve_publication(
        producer_id="canonical_live_publisher",
        producer_run_id="run-1",
        symbol="SPY",
        timeframe="5m",
    )
    assert plan.should_execute is True
    with sqlite3.connect(repository.database_path) as connection:
        state = connection.execute(
            """SELECT status FROM opportunity_publication_commands
               WHERE producer_run_id = 'run-1'"""
        ).fetchone()[0]
    assert state == "RESERVED"

    bars = pd.DataFrame(
        [
            {
                "timestamp": BASE_TIME + timedelta(minutes=5),
                "open": 900.0,
                "high": 901.0,
                "low": 899.0,
                "close": 900.5,
                "volume": 9000,
            },
            {
                "timestamp": BASE_TIME - timedelta(minutes=5),
                "open": 500.0,
                "high": 501.0,
                "low": 499.0,
                "close": 500.5,
                "volume": 1000,
            }
        ]
    )
    context = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=BASE_TIME,
        request_started_at=BASE_TIME - timedelta(seconds=3),
        bars=bars,
        data_dependencies={
            "bars": DataDependencyStatus(
                name="bars",
                available=True,
                retrieved_at=BASE_TIME - timedelta(seconds=1),
                content_sha256="a" * 64,
            )
        },
        publication_state=PublicationState.RESEARCH_ONLY,
        config_version="research_v1",
    )
    result = QXEvaluationResult(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=BASE_TIME,
        request_started_at=BASE_TIME - timedelta(seconds=3),
        publication_state=PublicationState.RESEARCH_ONLY,
        current_lifecycle_state=LifecycleState.NO_SETUP,
        evidence_summary=[],
        reason_codes=["NO_SETUP"],
        config_version="research_v1",
        pipeline_version="core_v1",
        data_dependencies=context.data_dependencies,
        evaluated_bar_window_sha256=evaluated_bar_window_sha256(
            filter_bars_at_or_before(bars, BASE_TIME),
            "5m",
        ),
    )
    first = publisher.publish_reserved(
        plan=plan,
        result=result,
        context=context,
        producer_id="canonical_live_publisher",
        producer_run_id="run-1",
        expires_at=BASE_TIME + timedelta(minutes=15),
        freshness_policy_version="approved_test_v1",
    )
    repeated = publisher.reserve_publication(
        producer_id="canonical_live_publisher",
        producer_run_id="run-1",
        symbol="SPY",
        timeframe="5m",
    )
    assert repeated.should_execute is False
    assert repeated.existing_record is not None
    assert first.evaluation_id == repeated.existing_record.evaluation_id
    assert first.idempotency_key.startswith("qxcmd1_")
    assert len(first.idempotency_key) == 71
    visible_bars = filter_bars_at_or_before(bars, BASE_TIME)
    assert first.bar_window_sha256 == evaluated_bar_window_sha256(visible_bars, "5m")


def test_failed_publication_reservation_can_be_abandoned_immediately(tmp_path) -> None:
    repository = _repository(tmp_path)
    publisher = OpportunityPublisher(repository, environment_id="local")
    plan = publisher.reserve_publication(
        producer_id="canonical_live_publisher",
        producer_run_id="run-failed",
        symbol="SPY",
        timeframe="5m",
    )

    assert publisher.abandon_reserved(
        plan,
        failure_code="PUBLICATION_VALIDATION_FAILED",
    ) is True

    retried = publisher.reserve_publication(
        producer_id="canonical_live_publisher",
        producer_run_id="run-failed",
        symbol="SPY",
        timeframe="5m",
    )
    assert retried.should_execute is True
    assert retried.reservation.attempt_count == 2


def test_point_in_time_window_is_sorted_before_pipeline_hashing() -> None:
    bars = pd.DataFrame(
        [
            {
                "timestamp": BASE_TIME,
                "open": 501.0,
                "high": 502.0,
                "low": 500.0,
                "close": 501.5,
                "volume": 1100,
            },
            {
                "timestamp": BASE_TIME - timedelta(minutes=5),
                "open": 500.0,
                "high": 501.0,
                "low": 499.0,
                "close": 500.5,
                "volume": 1000,
            },
        ]
    )
    visible = filter_bars_at_or_before(bars, BASE_TIME)
    assert list(visible["timestamp"]) == sorted(visible["timestamp"])
    digest = evaluated_bar_window_sha256(visible, "5m")
    with pytest.raises(ValueError, match="canonical ascending order"):
        evaluated_bar_window_sha256(visible.iloc[::-1], "5m")
    assert len(digest) == 64


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("schema_version", "qx.opportunity-record.v999"),
        ("decision_payload_json", '{"tampered":true}'),
    ],
)
def test_corrupt_stored_record_returns_integrity_conflict(
    tmp_path,
    column: str,
    value: str,
) -> None:
    repository = _repository(tmp_path)
    record = _record(repository, 1, state=LifecycleState.ARMED, evaluated_at=BASE_TIME)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(
            f"UPDATE opportunity_evaluations SET {column} = ? WHERE evaluation_id = ?",
            (value, record.evaluation_id),
        )
    client = _client(repository)
    detail = client.get(f"/api/v2/qx/opportunities/{record.evaluation_id}")
    listing = client.get(
        "/api/v2/qx/opportunities",
        params={"query_as_of": (BASE_TIME + timedelta(minutes=1)).isoformat()},
    )
    assert detail.status_code == 409
    assert listing.status_code == 409


def test_api_etag_hashes_exact_deterministic_detail_representation(tmp_path) -> None:
    repository = _repository(tmp_path)
    first = _record(repository, 1, state=LifecycleState.ARMED, evaluated_at=BASE_TIME)
    second = _record(
        repository,
        2,
        state=LifecycleState.TRIGGERED,
        evaluated_at=BASE_TIME + timedelta(minutes=5),
        symbol="QQQ",
    )
    client = _client(repository)
    first_response = client.get(f"/api/v2/qx/opportunities/{first.evaluation_id}")
    repeated = client.get(f"/api/v2/qx/opportunities/{first.evaluation_id}")
    changed = client.get(f"/api/v2/qx/opportunities/{second.evaluation_id}")
    assert first_response.content == repeated.content
    assert first_response.headers["etag"] == repeated.headers["etag"]
    assert first_response.headers["etag"] != changed.headers["etag"]
    not_modified = client.get(
        f"/api/v2/qx/opportunities/{first.evaluation_id}",
        headers={"If-None-Match": first_response.headers["etag"]},
    )
    assert not_modified.status_code == 304
    assert not_modified.content == b""


def test_list_order_filter_and_pagination_have_deterministic_etags(tmp_path) -> None:
    repository = _repository(tmp_path)
    _record(repository, 1, state=LifecycleState.ARMED, evaluated_at=BASE_TIME, symbol="SPY")
    _record(
        repository,
        2,
        state=LifecycleState.TRIGGERED,
        evaluated_at=BASE_TIME + timedelta(minutes=1),
        symbol="QQQ",
    )
    client = _client(repository)
    parameters = {"query_as_of": (BASE_TIME + timedelta(minutes=2)).isoformat(), "limit": 1}
    first_page = client.get("/api/v2/qx/opportunities", params=parameters)
    repeated = client.get("/api/v2/qx/opportunities", params=parameters)
    assert first_page.headers["etag"] == repeated.headers["etag"]
    body = first_page.json()
    assert body["items"][0]["symbol"] == "QQQ"
    assert body["has_more"] is True
    second_page = client.get(
        "/api/v2/qx/opportunities",
        params={**parameters, "cursor": body["next_cursor"]},
    )
    assert second_page.json()["items"][0]["symbol"] == "SPY"
    assert first_page.headers["etag"] != second_page.headers["etag"]
    filtered = client.get(
        "/api/v2/qx/opportunities",
        params={"query_as_of": parameters["query_as_of"], "symbols": "SPY"},
    )
    assert filtered.headers["etag"] != first_page.headers["etag"]


def test_malformed_identity_and_cursor_are_rejected(tmp_path) -> None:
    client = _client(_repository(tmp_path))
    assert client.get("/api/v2/qx/opportunities/not-an-id").status_code == 422
    assert client.get("/api/v2/qx/opportunities", params={"cursor": "bad"}).status_code == 422


def _client(repository: OpportunityRepository) -> TestClient:
    app = FastAPI()
    app.include_router(create_opportunity_router(repository, environment_id="local"))
    return TestClient(app)
