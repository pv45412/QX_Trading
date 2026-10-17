"""Canonical SQLite persistence for legacy-to-v2 shadow comparisons."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from pydantic import BaseModel, Field

from qx.pipeline.models import PIPELINE_VERSION, QXEvaluationResult
from qx.storage.connection import connect_sqlite


class ShadowTelemetryRecord(BaseModel):
    symbol: str
    timeframe: str
    evaluation_timestamp: datetime
    legacy_signal: Optional[str] = None
    legacy_direction: Optional[str] = None
    v2_lifecycle_state: Optional[str] = None
    v2_direction_score: Optional[float] = None
    v2_primary_playbook: Optional[str] = None
    structure_state: Optional[str] = None
    trend_regime: Optional[str] = None
    volatility_regime: Optional[str] = None
    gamma_regime: Optional[str] = None
    session_regime: Optional[str] = None
    direction_label: Optional[str] = None
    playbook_state: Optional[str] = None
    options_state: Optional[str] = None
    portfolio_state: Optional[str] = None
    evidence_coverage: Optional[float] = None
    coverage_status: Optional[str] = None
    data_as_of: Optional[datetime] = None
    data_freshness: dict[str, Any] = Field(default_factory=dict)
    stage_latencies: dict[str, float | int | str] = Field(default_factory=dict)
    v2_reason_codes: list[str] = Field(default_factory=list)
    market_driver_status: Optional[str] = None
    primary_driver: Optional[str] = None
    driver_strength: Optional[str] = None
    driver_persistence_state: Optional[str] = None
    driver_duration_seconds: Optional[int] = None
    driver_coverage_status: Optional[str] = None
    confirming_evidence_count: Optional[int] = None
    conflicting_evidence_count: Optional[int] = None
    agreement_status: str
    disagreement_category: Optional[str] = None
    legacy_latency_ms: Optional[float] = None
    v2_latency_ms: Optional[float] = None
    legacy_error: Optional[str] = None
    v2_error: Optional[str] = None
    publication_state: str
    config_version: str
    pipeline_version: str = PIPELINE_VERSION
    engine_versions: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ShadowTelemetryRepository:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS shadow_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    evaluation_timestamp TEXT NOT NULL,
                    legacy_signal TEXT,
                    legacy_direction TEXT,
                    v2_lifecycle_state TEXT,
                    v2_direction_score REAL,
                    v2_primary_playbook TEXT,
                    v2_reason_codes TEXT NOT NULL,
                    agreement_status TEXT NOT NULL,
                    disagreement_category TEXT,
                    legacy_latency_ms REAL,
                    v2_latency_ms REAL,
                    legacy_error TEXT,
                    v2_error TEXT,
                    publication_state TEXT NOT NULL,
                    config_version TEXT NOT NULL,
                    pipeline_version TEXT NOT NULL,
                    engine_versions TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            existing_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(shadow_telemetry)")
            }
            for name, column_type in _ADDITIVE_COLUMNS.items():
                if name not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE shadow_telemetry ADD COLUMN {name} {column_type}"
                    )

    def write(self, record: ShadowTelemetryRecord) -> int:
        self.initialize()
        with connect_sqlite(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO shadow_telemetry (
                    symbol,
                    timeframe,
                    evaluation_timestamp,
                    legacy_signal,
                    legacy_direction,
                    v2_lifecycle_state,
                    v2_direction_score,
                    v2_primary_playbook,
                    v2_reason_codes,
                    agreement_status,
                    disagreement_category,
                    legacy_latency_ms,
                    v2_latency_ms,
                    legacy_error,
                    v2_error,
                    publication_state,
                    config_version,
                    pipeline_version,
                    engine_versions,
                    structure_state,
                    trend_regime,
                    volatility_regime,
                    gamma_regime,
                    session_regime,
                    direction_label,
                    playbook_state,
                    options_state,
                    portfolio_state,
                    evidence_coverage,
                    coverage_status,
                    data_as_of,
                    data_freshness,
                    stage_latencies,
                    market_driver_status,
                    primary_driver,
                    driver_strength,
                    driver_persistence_state,
                    driver_duration_seconds,
                    driver_coverage_status,
                    confirming_evidence_count,
                    conflicting_evidence_count,
                    created_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    record.symbol.upper(),
                    record.timeframe,
                    record.evaluation_timestamp.isoformat(),
                    record.legacy_signal,
                    record.legacy_direction,
                    record.v2_lifecycle_state,
                    record.v2_direction_score,
                    record.v2_primary_playbook,
                    json.dumps(record.v2_reason_codes, separators=(",", ":")),
                    record.agreement_status,
                    record.disagreement_category,
                    record.legacy_latency_ms,
                    record.v2_latency_ms,
                    record.legacy_error,
                    record.v2_error,
                    record.publication_state,
                    record.config_version,
                    record.pipeline_version,
                    json.dumps(record.engine_versions, sort_keys=True, separators=(",", ":")),
                    record.structure_state,
                    record.trend_regime,
                    record.volatility_regime,
                    record.gamma_regime,
                    record.session_regime,
                    record.direction_label,
                    record.playbook_state,
                    record.options_state,
                    record.portfolio_state,
                    record.evidence_coverage,
                    record.coverage_status,
                    record.data_as_of.isoformat() if record.data_as_of else None,
                    json.dumps(record.data_freshness, sort_keys=True, separators=(",", ":")),
                    json.dumps(record.stage_latencies, sort_keys=True, separators=(",", ":")),
                    record.market_driver_status,
                    record.primary_driver,
                    record.driver_strength,
                    record.driver_persistence_state,
                    record.driver_duration_seconds,
                    record.driver_coverage_status,
                    record.confirming_evidence_count,
                    record.conflicting_evidence_count,
                    record.created_at.isoformat(),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a shadow telemetry row id")
            return int(cursor.lastrowid)

    def list_records(
        self,
        *,
        symbols: Optional[Sequence[str]] = None,
        limit: int = 5000,
    ) -> list[ShadowTelemetryRecord]:
        if limit < 1 or limit > 100_000:
            raise ValueError("Shadow telemetry limit must be between 1 and 100000")
        self.initialize()
        parameters: list[Any] = []
        where = ""
        if symbols:
            canonical_symbols = sorted({symbol.upper() for symbol in symbols})
            placeholders = ",".join("?" for _ in canonical_symbols)
            where = f"WHERE symbol IN ({placeholders})"
            parameters.extend(canonical_symbols)
        parameters.append(limit)
        query = f"""
            SELECT * FROM (
                SELECT *
                FROM shadow_telemetry
                {where}
                ORDER BY evaluation_timestamp DESC, id DESC
                LIMIT ?
            )
            ORDER BY evaluation_timestamp ASC, id ASC
        """
        with connect_sqlite(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, parameters).fetchall()
        return [_record_from_row(dict(row)) for row in rows]


_ADDITIVE_COLUMNS = {
    "structure_state": "TEXT",
    "trend_regime": "TEXT",
    "volatility_regime": "TEXT",
    "gamma_regime": "TEXT",
    "session_regime": "TEXT",
    "direction_label": "TEXT",
    "playbook_state": "TEXT",
    "options_state": "TEXT",
    "portfolio_state": "TEXT",
    "evidence_coverage": "REAL",
    "coverage_status": "TEXT",
    "data_as_of": "TEXT",
    "data_freshness": "TEXT NOT NULL DEFAULT '{}'",
    "stage_latencies": "TEXT NOT NULL DEFAULT '{}'",
    "market_driver_status": "TEXT",
    "primary_driver": "TEXT",
    "driver_strength": "TEXT",
    "driver_persistence_state": "TEXT",
    "driver_duration_seconds": "INTEGER",
    "driver_coverage_status": "TEXT",
    "confirming_evidence_count": "INTEGER",
    "conflicting_evidence_count": "INTEGER",
}


def _enum_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def build_shadow_record(
    *,
    symbol: str,
    timeframe: str,
    evaluation_timestamp: datetime,
    legacy_result: Any,
    legacy_latency_ms: Optional[float],
    v2_result: Optional[QXEvaluationResult],
    v2_latency_ms: Optional[float],
    config_version: str,
    legacy_error: Optional[str] = None,
    v2_error: Optional[str] = None,
) -> ShadowTelemetryRecord:
    legacy_direction_result = getattr(legacy_result, "direction_result", None)
    legacy_direction = _enum_value(getattr(legacy_direction_result, "bias", None))
    passed_veto = getattr(legacy_result, "passed_veto", None)
    legacy_signal = None if passed_veto is None else ("PASSED_VETO" if passed_veto else "VETOED")

    v2_direction = getattr(v2_result, "direction", None)
    v2_direction_label = _enum_value(getattr(v2_direction, "direction_label", None))
    if legacy_error:
        agreement_status = "ERROR"
        disagreement_category = "LEGACY_ERROR"
    elif v2_error:
        agreement_status = "ERROR"
        disagreement_category = "V2_ERROR"
    elif legacy_direction is None or v2_direction_label is None:
        agreement_status = "INDETERMINATE"
        disagreement_category = "MISSING_DIRECTION"
    elif legacy_direction == v2_direction_label:
        agreement_status = "AGREEMENT"
        disagreement_category = None
    else:
        agreement_status = "DISAGREEMENT"
        disagreement_category = "DIRECTION_MISMATCH"

    primary_playbook = getattr(v2_result, "primary_playbook_candidate", None)
    structure = getattr(v2_result, "structure", None)
    regime = getattr(v2_result, "market_regime", None)
    options = getattr(v2_result, "options_expression", None)
    portfolio = getattr(v2_result, "portfolio_risk", None)
    dependencies = dict(getattr(v2_result, "data_dependencies", {}) or {})
    bars_dependency = dependencies.get("bars")
    data_as_of = getattr(bars_dependency, "data_as_of", None)
    data_freshness = {
        name: (
            dependency.model_dump(mode="json")
            if hasattr(dependency, "model_dump")
            else dict(dependency)
            if isinstance(dependency, dict)
            else {"freshness": str(dependency)}
        )
        for name, dependency in dependencies.items()
    }
    market_driver = getattr(v2_result, "market_driver", None)
    md_status = _enum_value(getattr(market_driver, "status", None))
    primary = getattr(market_driver, "primary_driver", None)
    primary_archetype = _enum_value(getattr(primary, "driver_id", getattr(primary, "archetype", None)))
    primary_strength = _enum_value(getattr(primary, "strength", None))
    persistence = getattr(primary, "persistence", getattr(market_driver, "driver_persistence", None))
    persistence_state = _enum_value(getattr(persistence, "state", None))
    duration_seconds = getattr(persistence, "duration_seconds", None)
    coverage = getattr(market_driver, "coverage", None)
    driver_coverage_status = _enum_value(getattr(coverage, "status", getattr(coverage, "coverage_status", None)))
    confirming_count = len(getattr(market_driver, "confirming_evidence", ()) or ()) if market_driver else None
    conflicting_count = len(getattr(market_driver, "conflicting_evidence", ()) or ()) if market_driver else None

    publication_state = (
        _enum_value(getattr(v2_result, "publication_state", None)) or "RESEARCH_ONLY"
    )
    return ShadowTelemetryRecord(
        symbol=symbol.upper(),
        timeframe=timeframe,
        evaluation_timestamp=evaluation_timestamp,
        legacy_signal=legacy_signal,
        legacy_direction=legacy_direction,
        v2_lifecycle_state=_enum_value(getattr(v2_result, "current_lifecycle_state", None)),
        v2_direction_score=getattr(v2_direction, "direction_score", None),
        v2_primary_playbook=getattr(primary_playbook, "playbook_id", None),
        structure_state=_enum_value(getattr(structure, "regime", None)),
        trend_regime=_enum_value(getattr(regime, "trend", None)),
        volatility_regime=_enum_value(getattr(regime, "volatility", None)),
        gamma_regime=_enum_value(getattr(regime, "gamma", None)),
        session_regime=_enum_value(getattr(regime, "session", None)),
        direction_label=v2_direction_label,
        playbook_state=_enum_value(getattr(primary_playbook, "state", None)),
        options_state=_enum_value(getattr(options, "state", None)),
        portfolio_state=_enum_value(getattr(portfolio, "state", None)),
        evidence_coverage=getattr(v2_direction, "direction_evidence_coverage", None),
        coverage_status=_enum_value(getattr(v2_direction, "coverage_status", None)),
        data_as_of=data_as_of,
        data_freshness=data_freshness,
        stage_latencies=dict(getattr(v2_result, "stage_latencies", {}) or {}),
        v2_reason_codes=list(getattr(v2_result, "reason_codes", ()) or ()),
        agreement_status=agreement_status,
        disagreement_category=disagreement_category,
        legacy_latency_ms=legacy_latency_ms,
        v2_latency_ms=v2_latency_ms,
        legacy_error=legacy_error,
        v2_error=v2_error,
        publication_state=publication_state,
        config_version=config_version,
        pipeline_version=getattr(v2_result, "pipeline_version", PIPELINE_VERSION),
        engine_versions=dict(getattr(v2_result, "engine_versions", {}) or {}),
        market_driver_status=md_status,
        primary_driver=primary_archetype,
        driver_strength=primary_strength,
        driver_persistence_state=persistence_state,
        driver_duration_seconds=duration_seconds,
        driver_coverage_status=driver_coverage_status,
        confirming_evidence_count=confirming_count,
        conflicting_evidence_count=conflicting_count,
    )


def _record_from_row(row: dict[str, Any]) -> ShadowTelemetryRecord:
    def decoded(name: str, default: Any) -> Any:
        value = row.get(name)
        return json.loads(value) if value else default

    return ShadowTelemetryRecord(
        symbol=row["symbol"],
        timeframe=row["timeframe"],
        evaluation_timestamp=row["evaluation_timestamp"],
        legacy_signal=row.get("legacy_signal"),
        legacy_direction=row.get("legacy_direction"),
        v2_lifecycle_state=row.get("v2_lifecycle_state"),
        v2_direction_score=row.get("v2_direction_score"),
        v2_primary_playbook=row.get("v2_primary_playbook"),
        structure_state=row.get("structure_state"),
        trend_regime=row.get("trend_regime"),
        volatility_regime=row.get("volatility_regime"),
        gamma_regime=row.get("gamma_regime"),
        session_regime=row.get("session_regime"),
        direction_label=row.get("direction_label"),
        playbook_state=row.get("playbook_state"),
        options_state=row.get("options_state"),
        portfolio_state=row.get("portfolio_state"),
        evidence_coverage=row.get("evidence_coverage"),
        coverage_status=row.get("coverage_status"),
        data_as_of=row.get("data_as_of"),
        data_freshness=decoded("data_freshness", {}),
        stage_latencies=decoded("stage_latencies", {}),
        v2_reason_codes=decoded("v2_reason_codes", []),
        agreement_status=row["agreement_status"],
        disagreement_category=row.get("disagreement_category"),
        legacy_latency_ms=row.get("legacy_latency_ms"),
        v2_latency_ms=row.get("v2_latency_ms"),
        legacy_error=row.get("legacy_error"),
        v2_error=row.get("v2_error"),
        publication_state=row["publication_state"],
        config_version=row["config_version"],
        pipeline_version=row["pipeline_version"],
        engine_versions=decoded("engine_versions", {}),
        market_driver_status=row.get("market_driver_status"),
        primary_driver=row.get("primary_driver"),
        driver_strength=row.get("driver_strength"),
        driver_persistence_state=row.get("driver_persistence_state"),
        driver_duration_seconds=row.get("driver_duration_seconds"),
        driver_coverage_status=row.get("driver_coverage_status"),
        confirming_evidence_count=row.get("confirming_evidence_count"),
        conflicting_evidence_count=row.get("conflicting_evidence_count"),
        created_at=row["created_at"],
    )
