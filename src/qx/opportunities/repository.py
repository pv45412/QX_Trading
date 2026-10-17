from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from pydantic import ValidationError

from qx.opportunities.identity import (
    command_identity,
    decode_cursor,
    encode_cursor,
    sha256_digest,
    stream_key,
    utc_timestamp,
)
from qx.opportunities.migrations import apply_opportunity_migrations
from qx.opportunities.models import (
    ObservationMode,
    OpportunityDetail,
    OpportunityListItem,
    OpportunityListResponse,
    OpportunityRecord,
    PublicationCommandState,
)
from qx.pipeline.models import LifecycleState
from qx.storage.connection import connect_sqlite


class OpportunityRepositoryError(RuntimeError):
    pass


class OpportunityIntegrityError(OpportunityRepositoryError):
    pass


class IdempotencyConflict(OpportunityRepositoryError):
    pass


class ReservationInProgress(OpportunityRepositoryError):
    pass


@dataclass(frozen=True)
class CommandReservation:
    idempotency_key: str
    state: PublicationCommandState
    should_execute: bool
    evaluation_id: str | None
    attempt_count: int


TERMINAL_STATES = {
    LifecycleState.BLOCKED.value,
    LifecycleState.NO_SETUP.value,
    LifecycleState.NOT_TRADEABLE.value,
    LifecycleState.EXPIRED.value,
    LifecycleState.OPTIONS_NOT_SUITABLE.value,
    LifecycleState.PORTFOLIO_VETOED.value,
}
EVALUATION_ID_PATTERN = re.compile(r"^qxev1_[0-9a-f]{32}$")
SENSITIVE_KEYS = {
    "account_id",
    "account_equity",
    "buying_power_available",
    "positions",
    "existing_related_positions",
    "access_token",
    "refresh_token",
    "client_secret",
    "oauth_token",
    "api_secret",
}


class OpportunityRepository:
    def __init__(
        self,
        database_path: Path,
        *,
        reconciliation_ttl: timedelta = timedelta(minutes=5),
        initialize: bool = True,
    ) -> None:
        self.database_path = Path(database_path)
        self.reconciliation_ttl = reconciliation_ttl
        if initialize:
            self.initialize()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        apply_opportunity_migrations(str(self.database_path))

    def reserve_command(
        self,
        *,
        idempotency_key: str,
        payload_hash: str,
        producer_id: str,
        producer_run_id: str,
        now: datetime | None = None,
    ) -> CommandReservation:
        timestamp = _aware(now or datetime.now(timezone.utc))
        with closing(self._write_connection()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM opportunity_publication_commands WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """INSERT INTO opportunity_publication_commands (
                        idempotency_key, payload_hash, producer_id, producer_run_id, status,
                        evaluation_id, attempt_count, reserved_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'RESERVED', NULL, 1, ?, ?)""",
                    (
                        idempotency_key,
                        payload_hash,
                        producer_id,
                        producer_run_id,
                        utc_timestamp(timestamp),
                        utc_timestamp(timestamp),
                    ),
                )
                connection.commit()
                return CommandReservation(
                    idempotency_key,
                    PublicationCommandState.RESERVED,
                    True,
                    None,
                    1,
                )
            if row["payload_hash"] != payload_hash:
                connection.rollback()
                raise IdempotencyConflict("Idempotency key payload hash mismatch")
            state = PublicationCommandState(row["status"])
            if state is PublicationCommandState.COMMITTED:
                connection.commit()
                return CommandReservation(
                    idempotency_key,
                    state,
                    False,
                    row["evaluation_id"],
                    row["attempt_count"],
                )
            if state is PublicationCommandState.RESERVED:
                reserved_at = _parse(row["reserved_at"])
                if timestamp - reserved_at <= self.reconciliation_ttl:
                    connection.rollback()
                    raise ReservationInProgress("Publication command is already reserved")
                committed = connection.execute(
                    "SELECT evaluation_id FROM opportunity_evaluations WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if committed is not None:
                    connection.rollback()
                    raise OpportunityRepositoryError(
                        "Reserved command has an immutable record and requires reconciliation"
                    )
                connection.execute(
                    """UPDATE opportunity_publication_commands
                       SET status = 'ABANDONED', abandoned_at = ?, updated_at = ?,
                           failure_code = 'RESERVATION_TTL_EXCEEDED'
                       WHERE idempotency_key = ? AND status = 'RESERVED'""",
                    (utc_timestamp(timestamp), utc_timestamp(timestamp), idempotency_key),
                )
            attempt_count = int(row["attempt_count"]) + 1
            connection.execute(
                """UPDATE opportunity_publication_commands
                   SET status = 'RESERVED', producer_id = ?, producer_run_id = ?,
                       evaluation_id = NULL, attempt_count = ?, reserved_at = ?, updated_at = ?,
                       committed_at = NULL, abandoned_at = NULL, failure_code = NULL
                   WHERE idempotency_key = ? AND status = 'ABANDONED'""",
                (
                    producer_id,
                    producer_run_id,
                    attempt_count,
                    utc_timestamp(timestamp),
                    utc_timestamp(timestamp),
                    idempotency_key,
                ),
            )
            if connection.total_changes != 2 and state is PublicationCommandState.RESERVED:
                connection.rollback()
                raise OpportunityRepositoryError("Publication command reconciliation failed")
            if connection.total_changes != 1 and state is PublicationCommandState.ABANDONED:
                connection.rollback()
                raise OpportunityRepositoryError("Abandoned command could not be re-reserved")
            connection.commit()
            return CommandReservation(
                idempotency_key,
                PublicationCommandState.RESERVED,
                True,
                None,
                attempt_count,
            )

    def reconcile_abandoned(self, *, now: datetime | None = None) -> int:
        timestamp = _aware(now or datetime.now(timezone.utc))
        cutoff = timestamp - self.reconciliation_ttl
        with closing(self._write_connection()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE opportunity_publication_commands
                   SET status = 'ABANDONED', abandoned_at = ?, updated_at = ?,
                       failure_code = 'RESERVATION_TTL_EXCEEDED'
                   WHERE status = 'RESERVED' AND reserved_at < ?
                     AND NOT EXISTS (
                         SELECT 1 FROM opportunity_evaluations evaluation
                         WHERE evaluation.idempotency_key =
                               opportunity_publication_commands.idempotency_key
                     )""",
                (
                    utc_timestamp(timestamp),
                    utc_timestamp(timestamp),
                    utc_timestamp(cutoff),
                ),
            )
            connection.commit()
            return cursor.rowcount

    def abandon_command(
        self,
        idempotency_key: str,
        *,
        failure_code: str,
        now: datetime | None = None,
    ) -> bool:
        timestamp = _aware(now or datetime.now(timezone.utc))
        normalized_failure = failure_code.strip().upper()
        if not normalized_failure or len(normalized_failure) > 100:
            raise ValueError("Invalid opportunity publication failure code")
        with closing(self._write_connection()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE opportunity_publication_commands
                   SET status = 'ABANDONED', abandoned_at = ?, updated_at = ?,
                       failure_code = ?
                   WHERE idempotency_key = ? AND status = 'RESERVED'
                     AND NOT EXISTS (
                         SELECT 1 FROM opportunity_evaluations evaluation
                         WHERE evaluation.idempotency_key =
                               opportunity_publication_commands.idempotency_key
                     )""",
                (
                    utc_timestamp(timestamp),
                    utc_timestamp(timestamp),
                    normalized_failure,
                    idempotency_key,
                ),
            )
            connection.commit()
            return cursor.rowcount == 1

    def commit_record(self, record: OpportunityRecord) -> OpportunityRecord:
        _validate_record(record)
        with closing(self._write_connection()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            command = connection.execute(
                """SELECT status, evaluation_id
                   FROM opportunity_publication_commands
                   WHERE idempotency_key = ?""",
                (record.idempotency_key,),
            ).fetchone()
            if command is None or command["status"] != PublicationCommandState.RESERVED.value:
                connection.rollback()
                raise OpportunityRepositoryError("Record commit requires a RESERVED command")
            try:
                connection.execute(
                    """INSERT INTO opportunity_evaluations (
                        evaluation_id, idempotency_key, schema_version, observation_mode,
                        environment_id, producer_id, producer_run_id, symbol, timeframe,
                        horizon_context, evaluation_timestamp, request_started_at, recorded_at,
                        expires_at, freshness_policy_version, publication_state, lifecycle_state,
                        pipeline_version, config_version, engine_versions_json, direction,
                        primary_playbook_id, source_setup_reference, reason_codes_json,
                        evidence_coverage, coverage_status, data_dependencies_json,
                        decision_payload_json, input_fingerprint, bar_window_sha256,
                        result_sha256, stream_key, supersedes_evaluation_id
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )""",
                    _record_values(record),
                )
                updated = connection.execute(
                    """UPDATE opportunity_publication_commands
                       SET status = 'COMMITTED', evaluation_id = ?, committed_at = ?, updated_at = ?
                       WHERE idempotency_key = ? AND status = 'RESERVED'""",
                    (
                        record.evaluation_id,
                        utc_timestamp(record.recorded_at),
                        utc_timestamp(record.recorded_at),
                        record.idempotency_key,
                    ),
                )
                if updated.rowcount != 1:
                    raise OpportunityRepositoryError("Command commit transition failed")
                connection.commit()
            except (sqlite3.Error, OpportunityRepositoryError) as exc:
                connection.rollback()
                if isinstance(exc, OpportunityRepositoryError):
                    raise
                raise OpportunityRepositoryError("Immutable opportunity commit failed") from exc
        return record

    def get_detail(self, evaluation_id: str, *, environment_id: str) -> OpportunityDetail | None:
        try:
            with closing(self._read_connection()) as connection:
                row = connection.execute(
                    """SELECT * FROM opportunity_evaluations
                       WHERE evaluation_id = ? AND observation_mode = 'LIVE'
                         AND environment_id = ?""",
                    (evaluation_id, environment_id),
                ).fetchone()
        except sqlite3.Error as exc:
            raise OpportunityRepositoryError("Opportunity detail read failed") from exc
        if row is None:
            return None
        try:
            return _detail(_record(row))
        except (TypeError, ValueError, ValidationError) as exc:
            raise OpportunityIntegrityError("Stored opportunity detail is invalid") from exc

    def get_record(self, evaluation_id: str, *, environment_id: str) -> OpportunityRecord | None:
        try:
            with closing(self._read_connection()) as connection:
                row = connection.execute(
                    """SELECT * FROM opportunity_evaluations
                       WHERE evaluation_id = ? AND observation_mode = 'LIVE'
                         AND environment_id = ?""",
                    (evaluation_id, environment_id),
                ).fetchone()
        except sqlite3.Error as exc:
            raise OpportunityRepositoryError("Opportunity record read failed") from exc
        return _record(row) if row is not None else None

    def list_latest(
        self,
        *,
        environment_id: str,
        query_as_of: datetime,
        knowledge_as_of: datetime | None = None,
        evaluated_after: datetime | None = None,
        symbols: Iterable[str] = (),
        timeframe: str | None = None,
        states: Iterable[str] = (),
        publication_states: Iterable[str] = (),
        direction: str | None = None,
        playbook_id: str | None = None,
        horizon_context: str | None = None,
        include_terminal: bool = False,
        include_blocked: bool = False,
        fresh_only: bool = True,
        limit: int = 25,
        cursor: str | None = None,
    ) -> OpportunityListResponse:
        bounded_limit = max(1, min(limit, 100))
        as_of = _aware(query_as_of)
        knowledge = _aware(knowledge_as_of or datetime.now(timezone.utc))
        requested_publications = tuple(dict.fromkeys(publication_states))
        display_publications = requested_publications or ("VERIFIED", "RESEARCH_ONLY")
        if include_blocked and "BLOCKED" not in display_publications:
            display_publications = (*display_publications, "BLOCKED")
        hard_eligible_publications = ("VERIFIED", "RESEARCH_ONLY", "BLOCKED")

        hard_where = [
            "observation_mode = 'LIVE'",
            "environment_id = ?",
            f"publication_state IN ({','.join('?' for _ in hard_eligible_publications)})",
            "evaluation_timestamp <= ?",
            "recorded_at <= ?",
        ]
        parameters: list[object] = [
            environment_id,
            *hard_eligible_publications,
            utc_timestamp(as_of),
            utc_timestamp(knowledge),
        ]
        if fresh_only:
            hard_where.append("expires_at > ?")
            parameters.append(utc_timestamp(as_of))
        if evaluated_after is not None:
            hard_where.append("evaluation_timestamp >= ?")
            parameters.append(utc_timestamp(_aware(evaluated_after)))

        presentation_where = [
            "stream_rank = 1",
            f"publication_state IN ({','.join('?' for _ in display_publications)})",
        ]
        parameters.extend(display_publications)
        symbol_values = tuple(dict.fromkeys(symbol.upper() for symbol in symbols))
        if symbol_values:
            presentation_where.append(f"symbol IN ({','.join('?' for _ in symbol_values)})")
            parameters.extend(symbol_values)
        if timeframe:
            presentation_where.append("timeframe = ?")
            parameters.append(timeframe.lower())
        state_values = tuple(dict.fromkeys(states))
        if state_values:
            presentation_where.append(f"lifecycle_state IN ({','.join('?' for _ in state_values)})")
            parameters.extend(state_values)
        elif not include_terminal:
            excluded_terminal_states = TERMINAL_STATES - (
                {LifecycleState.BLOCKED.value} if include_blocked else set()
            )
            presentation_where.append(
                f"lifecycle_state NOT IN ({','.join('?' for _ in excluded_terminal_states)})"
            )
            parameters.extend(sorted(excluded_terminal_states))
        if direction:
            if direction == "UNAVAILABLE":
                presentation_where.append("direction IS NULL")
            else:
                presentation_where.append("direction = ?")
                parameters.append(direction)
        if playbook_id:
            presentation_where.append("primary_playbook_id = ?")
            parameters.append(playbook_id)
        if horizon_context:
            presentation_where.append("horizon_context = ?")
            parameters.append(horizon_context)
        if cursor:
            decoded = decode_cursor(cursor)
            expected = {"evaluation_timestamp", "recorded_at", "evaluation_id"}
            if set(decoded) != expected or not all(
                isinstance(decoded[field], str) and decoded[field]
                for field in expected
            ):
                raise ValueError("Invalid opportunity cursor fields")
            presentation_where.append(
                "(evaluation_timestamp, recorded_at, evaluation_id) < (?, ?, ?)"
            )
            parameters.extend(
                [
                    decoded["evaluation_timestamp"],
                    decoded["recorded_at"],
                    decoded["evaluation_id"],
                ]
            )

        sql = f"""
            WITH eligible AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY stream_key
                    ORDER BY evaluation_timestamp DESC, recorded_at DESC, evaluation_id DESC
                ) AS stream_rank
                FROM opportunity_evaluations
                WHERE {' AND '.join(hard_where)}
            )
            SELECT * FROM eligible
            WHERE {' AND '.join(presentation_where)}
            ORDER BY evaluation_timestamp DESC, recorded_at DESC, evaluation_id DESC
            LIMIT ?
        """
        parameters.append(bounded_limit + 1)
        try:
            with closing(self._read_connection()) as connection:
                rows = connection.execute(sql, parameters).fetchall()
        except sqlite3.Error as exc:
            raise OpportunityRepositoryError("Opportunity list read failed") from exc
        has_more = len(rows) > bounded_limit
        selected = rows[:bounded_limit]
        try:
            items = [_list_item(_record(row), as_of) for row in selected]
        except (TypeError, ValueError, ValidationError) as exc:
            raise OpportunityIntegrityError("Stored opportunity list item is invalid") from exc
        next_cursor = None
        if has_more and selected:
            last = selected[-1]
            next_cursor = encode_cursor(
                {
                    "evaluation_timestamp": last["evaluation_timestamp"],
                    "recorded_at": last["recorded_at"],
                    "evaluation_id": last["evaluation_id"],
                }
            )
        return OpportunityListResponse(
            generated_at=as_of,
            query_as_of=as_of,
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    def _write_connection(self) -> sqlite3.Connection:
        connection = connect_sqlite(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _read_connection(self) -> sqlite3.Connection:
        if not self.database_path.is_file():
            raise OpportunityRepositoryError("Opportunity database is unavailable")
        uri = self.database_path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        return connection


def _record_values(record: OpportunityRecord) -> tuple[object, ...]:
    return (
        record.evaluation_id,
        record.idempotency_key,
        record.schema_version,
        record.observation_mode.value,
        record.environment_id,
        record.producer_id,
        record.producer_run_id,
        record.symbol,
        record.timeframe,
        record.horizon_context,
        utc_timestamp(record.evaluation_timestamp),
        utc_timestamp(record.request_started_at) if record.request_started_at else None,
        utc_timestamp(record.recorded_at),
        utc_timestamp(record.expires_at),
        record.freshness_policy_version,
        record.publication_state,
        record.lifecycle_state.value,
        record.pipeline_version,
        record.config_version,
        json.dumps(record.engine_versions, sort_keys=True, separators=(",", ":")),
        record.direction,
        record.primary_playbook_id,
        record.source_setup_reference,
        json.dumps(record.reason_codes, separators=(",", ":")),
        record.evidence_coverage,
        record.coverage_status,
        json.dumps(record.data_dependencies, sort_keys=True, separators=(",", ":")),
        json.dumps(record.decision_payload, sort_keys=True, separators=(",", ":")),
        record.input_fingerprint,
        record.bar_window_sha256,
        record.result_sha256,
        record.stream_key,
        record.supersedes_evaluation_id,
    )


def _list_item(record: OpportunityRecord, as_of: datetime) -> OpportunityListItem:
    decision = record.decision_payload
    playbook = decision.get("primary_playbook_candidate") or {}
    trigger_result = decision.get("trigger") or {}
    tradeability = decision.get("tradeability") or {}
    options = decision.get("options_expression") or {}
    portfolio = decision.get("portfolio_risk") or {}
    return OpportunityListItem(
        evaluation_id=record.evaluation_id,
        source_mode=record.observation_mode,
        symbol=record.symbol,
        timeframe=record.timeframe,
        horizon_context=record.horizon_context,
        evaluation_timestamp=record.evaluation_timestamp,
        recorded_at=record.recorded_at,
        expires_at=record.expires_at,
        publication_state=record.publication_state,
        lifecycle_state=record.lifecycle_state,
        pipeline_version=record.pipeline_version,
        config_version=record.config_version,
        direction=record.direction,
        primary_playbook_id=record.primary_playbook_id,
        trigger=_first_value(trigger_result.get("trigger_price"), playbook.get("trigger_price")),
        trigger_source=playbook.get("trigger_source_type"),
        invalidation=_first_value(
            trigger_result.get("invalidation_price"),
            playbook.get("invalidation_price"),
        ),
        tradeability_state=tradeability.get("state"),
        options_state=options.get("state"),
        portfolio_state=portfolio.get("state"),
        reason_codes=record.reason_codes,
        evidence_coverage=record.evidence_coverage,
        coverage_status=record.coverage_status,
        data_dependencies=record.data_dependencies,
        market_driver=record.market_driver or decision.get("market_driver"),
        visibility_state="CURRENT" if record.expires_at > as_of else "STALE",
    )


def _detail(record: OpportunityRecord) -> OpportunityDetail:
    return OpportunityDetail(
        evaluation_id=record.evaluation_id,
        symbol=record.symbol,
        timeframe=record.timeframe,
        horizon_context=record.horizon_context,
        evaluation_timestamp=record.evaluation_timestamp,
        request_started_at=record.request_started_at,
        recorded_at=record.recorded_at,
        expires_at=record.expires_at,
        freshness_policy_version=record.freshness_policy_version,
        publication_state=record.publication_state,
        lifecycle_state=record.lifecycle_state,
        pipeline_version=record.pipeline_version,
        config_version=record.config_version,
        engine_versions=record.engine_versions,
        input_fingerprint=record.input_fingerprint,
        result_sha256=record.result_sha256,
        decision=record.decision_payload,
    )


def _record(row: sqlite3.Row) -> OpportunityRecord:
    try:
        record = OpportunityRecord(
            evaluation_id=row["evaluation_id"],
            idempotency_key=row["idempotency_key"],
            schema_version=row["schema_version"],
            observation_mode=ObservationMode(row["observation_mode"]),
            environment_id=row["environment_id"],
            producer_id=row["producer_id"],
            producer_run_id=row["producer_run_id"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            horizon_context=row["horizon_context"],
            evaluation_timestamp=_parse(row["evaluation_timestamp"]),
            request_started_at=(
                _parse(row["request_started_at"]) if row["request_started_at"] else None
            ),
            recorded_at=_parse(row["recorded_at"]),
            expires_at=_parse(row["expires_at"]),
            freshness_policy_version=row["freshness_policy_version"],
            publication_state=row["publication_state"],
            lifecycle_state=LifecycleState(row["lifecycle_state"]),
            pipeline_version=row["pipeline_version"],
            config_version=row["config_version"],
            engine_versions=json.loads(row["engine_versions_json"]),
            direction=row["direction"],
            primary_playbook_id=row["primary_playbook_id"],
            source_setup_reference=row["source_setup_reference"],
            reason_codes=json.loads(row["reason_codes_json"]),
            evidence_coverage=row["evidence_coverage"],
            coverage_status=row["coverage_status"],
            data_dependencies=json.loads(row["data_dependencies_json"]),
            market_driver=json.loads(row["decision_payload_json"]).get("market_driver"),
            decision_payload=json.loads(row["decision_payload_json"]),
            input_fingerprint=row["input_fingerprint"],
            bar_window_sha256=row["bar_window_sha256"],
            result_sha256=row["result_sha256"],
            stream_key=row["stream_key"],
            supersedes_evaluation_id=row["supersedes_evaluation_id"],
        )
        _validate_record(record)
        return record
    except OpportunityIntegrityError:
        raise
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, ValidationError) as exc:
        raise OpportunityIntegrityError("Stored opportunity record failed validation") from exc


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _first_value(*values: object) -> object:
    return next((value for value in values if value is not None), None)


def _validate_record(record: OpportunityRecord) -> None:
    if record.schema_version != "qx.opportunity-record.v1":
        raise OpportunityIntegrityError("Unsupported opportunity record schema")
    if record.observation_mode is not ObservationMode.LIVE:
        raise OpportunityIntegrityError("Only LIVE records may enter the opportunity store")
    if record.pipeline_version != "core_v1":
        raise OpportunityIntegrityError("Opportunity pipeline version must be core_v1")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (
            record.environment_id,
            record.producer_id,
            record.producer_run_id,
            record.symbol,
            record.timeframe,
            record.freshness_policy_version,
        )
    ):
        raise OpportunityIntegrityError("Opportunity immutable identity fields are required")
    if record.symbol != record.symbol.upper() or record.timeframe != record.timeframe.lower():
        raise OpportunityIntegrityError("Opportunity symbol/timeframe are not canonical")
    expected_command = command_identity(
        environment_id=record.environment_id,
        producer_id=record.producer_id,
        producer_run_id=record.producer_run_id,
        symbol=record.symbol,
        timeframe=record.timeframe,
    )
    if record.idempotency_key != expected_command:
        raise OpportunityIntegrityError("Opportunity command identity mismatch")
    expected_stream = stream_key(
        environment_id=record.environment_id,
        observation_mode=record.observation_mode.value,
        symbol=record.symbol,
        timeframe=record.timeframe,
        pipeline_version=record.pipeline_version,
        config_version=record.config_version,
    )
    if record.stream_key != expected_stream:
        raise OpportunityIntegrityError("Opportunity stream identity mismatch")
    if not EVALUATION_ID_PATTERN.fullmatch(record.evaluation_id):
        raise OpportunityIntegrityError("Malformed evaluation identity")
    if record.request_started_at and record.request_started_at > record.evaluation_timestamp:
        raise OpportunityIntegrityError("Request start cannot follow evaluation time")
    if record.recorded_at < record.evaluation_timestamp:
        raise OpportunityIntegrityError("Recorded time cannot precede evaluation time")
    if record.expires_at <= record.evaluation_timestamp:
        raise OpportunityIntegrityError("Opportunity expiry must follow evaluation time")
    if any(
        len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
        for value in (
            record.input_fingerprint,
            record.bar_window_sha256,
            record.result_sha256,
        )
    ):
        raise OpportunityIntegrityError("Opportunity digests must be lowercase SHA-256")
    expected_result = sha256_digest(
        {"schema_version": "qx.opportunity-decision.v1", "decision": record.decision_payload}
    )
    if record.result_sha256 != expected_result:
        raise OpportunityIntegrityError("Opportunity decision digest mismatch")
    _validate_decision_projection(record)
    bars = record.data_dependencies.get("bars")
    if not isinstance(bars, dict):
        raise OpportunityIntegrityError("LIVE opportunity requires bar provenance")
    retrieved_at = _dependency_timestamp(bars.get("retrieved_at"))
    data_as_of = _dependency_timestamp(bars.get("data_as_of"))
    content_sha256 = bars.get("content_sha256")
    if retrieved_at is None or retrieved_at > record.evaluation_timestamp:
        raise OpportunityIntegrityError("Bar retrieval is not point-in-time visible")
    if data_as_of is not None and data_as_of > record.evaluation_timestamp:
        raise OpportunityIntegrityError("Bar data_as_of exceeds evaluation time")
    if not isinstance(content_sha256, str) or len(content_sha256) != 64:
        raise OpportunityIntegrityError("Validated bar content digest is required")
    sensitive = _find_sensitive_key(record.decision_payload)
    if sensitive is not None:
        raise OpportunityIntegrityError(
            f"Sensitive opportunity field is prohibited: {sensitive}"
        )


def _validate_decision_projection(record: OpportunityRecord) -> None:
    required = {
        "symbol",
        "timeframe",
        "evaluation_timestamp",
        "request_started_at",
        "publication_state",
        "current_lifecycle_state",
        "evidence_summary",
        "reason_codes",
        "config_version",
        "pipeline_version",
        "engine_versions",
        "stage_latencies",
        "data_dependencies",
    }
    if not required.issubset(record.decision_payload):
        raise OpportunityIntegrityError("Opportunity decision projection is incomplete")
    decision = record.decision_payload
    evaluation_timestamp = _dependency_timestamp(decision.get("evaluation_timestamp"))
    request_started_at = _dependency_timestamp(decision.get("request_started_at"))
    if (
        decision.get("symbol") != record.symbol
        or decision.get("timeframe") != record.timeframe
        or evaluation_timestamp != record.evaluation_timestamp
        or request_started_at != record.request_started_at
        or decision.get("publication_state") != record.publication_state
        or decision.get("current_lifecycle_state") != record.lifecycle_state.value
        or decision.get("config_version") != record.config_version
        or decision.get("pipeline_version") != record.pipeline_version
        or decision.get("engine_versions") != record.engine_versions
        or decision.get("reason_codes") != record.reason_codes
    ):
        raise OpportunityIntegrityError("Opportunity decision projection does not match record")


def _dependency_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise OpportunityIntegrityError("Dependency timestamp must be serialized UTC text")
    try:
        return _parse(value)
    except ValueError as exc:
        raise OpportunityIntegrityError("Dependency timestamp is invalid") from exc


def _find_sensitive_key(value: object) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                return str(key)
            nested = _find_sensitive_key(item)
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for item in value:
            nested = _find_sensitive_key(item)
            if nested is not None:
                return nested
    return None
