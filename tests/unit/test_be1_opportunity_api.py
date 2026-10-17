from __future__ import annotations

import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from qx.interfaces import qx_v2
from qx.interfaces.opportunities import create_opportunity_router
from qx.interfaces.web import create_app
from qx.models.rules import PublicationState
from qx.opportunities.repository import OpportunityRepository
from qx.opportunities.migrations import (
    MIGRATION_001,
    OpportunityMigrationError,
    apply_opportunity_migrations,
)
from qx.pipeline.models import LifecycleState, QXEvaluationResult


def test_missing_runtime_database_is_not_created_by_read_api(tmp_path) -> None:
    database = tmp_path / "missing.db"
    app = create_app(
        database=database,
        cache_dir=tmp_path / "bars",
        configure_canonical_providers=False,
    )
    response = TestClient(app).get("/api/v2/qx/opportunities")
    assert response.status_code == 503
    assert not database.exists()


def test_initialized_runtime_database_exposes_read_only_opportunity_api(tmp_path) -> None:
    database = tmp_path / "runtime.db"
    OpportunityRepository(database)
    app = create_app(
        database=database,
        cache_dir=tmp_path / "bars",
        configure_canonical_providers=False,
    )
    response = TestClient(app).get(
        "/api/v2/qx/opportunities",
        params={"query_as_of": "2026-09-16T14:30:00Z"},
    )
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.headers["etag"].startswith('"')


def test_checksum_drift_disables_opportunity_api_without_reading_rows(
    tmp_path,
    monkeypatch,
) -> None:
    database = tmp_path / "runtime.db"
    OpportunityRepository(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE qx_schema_migrations SET migration_checksum = 'wrong' WHERE migration_id = ?",
            (MIGRATION_001.migration_id,),
        )
    reads = []

    def fail_if_read(*args, **kwargs):
        reads.append((args, kwargs))
        raise AssertionError("Untrusted opportunity rows must not be read")

    monkeypatch.setattr(OpportunityRepository, "list_latest", fail_if_read)
    app = create_app(
        database=database,
        cache_dir=tmp_path / "bars",
        configure_canonical_providers=False,
    )
    response = TestClient(app).get("/api/v2/qx/opportunities")
    assert response.status_code == 503
    assert response.json() == {
        "detail": {"code": "OPPORTUNITY_STORE_SCHEMA_INVALID"}
    }
    assert reads == []


def test_unledgered_schema_drift_disables_opportunity_api(tmp_path) -> None:
    database = tmp_path / "runtime.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE opportunity_evaluations (evaluation_id TEXT PRIMARY KEY)"
        )
    app = create_app(
        database=database,
        cache_dir=tmp_path / "bars",
        configure_canonical_providers=False,
    )
    response = TestClient(app).get("/api/v2/qx/opportunities")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "OPPORTUNITY_STORE_SCHEMA_INVALID"


def test_initialization_failure_mounts_only_sanitized_unavailable_router(
    tmp_path,
    monkeypatch,
) -> None:
    database = tmp_path / "runtime.db"
    database.touch()
    reads = []

    def fail_initialize(self):
        raise OpportunityMigrationError("secret SQL and filesystem details")

    def fail_if_read(*args, **kwargs):
        reads.append((args, kwargs))
        raise AssertionError("Unavailable router must not read opportunity rows")

    monkeypatch.setattr(OpportunityRepository, "initialize", fail_initialize)
    monkeypatch.setattr(OpportunityRepository, "list_latest", fail_if_read)
    monkeypatch.setattr(OpportunityRepository, "get_detail", fail_if_read)
    app = create_app(
        database=database,
        cache_dir=tmp_path / "bars",
        configure_canonical_providers=False,
    )
    client = TestClient(app)
    list_response = client.get("/api/v2/qx/opportunities")
    detail_response = client.get(
        "/api/v2/qx/opportunities/qxev1_00000000000070008000000000000001"
    )
    assert list_response.status_code == 503
    assert detail_response.status_code == 503
    assert list_response.json() == detail_response.json()
    assert "secret" not in list_response.text.lower()
    assert reads == []


def test_opportunity_api_recovers_after_clean_migration_reinitialization(tmp_path) -> None:
    database = tmp_path / "runtime.db"
    OpportunityRepository(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE qx_schema_migrations SET migration_checksum = 'wrong' WHERE migration_id = ?",
            (MIGRATION_001.migration_id,),
        )
    blocked_app = create_app(
        database=database,
        cache_dir=tmp_path / "bars",
        configure_canonical_providers=False,
    )
    assert TestClient(blocked_app).get("/api/v2/qx/opportunities").status_code == 503

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE qx_schema_migrations SET migration_checksum = ? WHERE migration_id = ?",
            (MIGRATION_001.checksum, MIGRATION_001.migration_id),
        )
    apply_opportunity_migrations(str(database))
    recovered_app = create_app(
        database=database,
        cache_dir=tmp_path / "bars",
        configure_canonical_providers=False,
    )
    recovered = TestClient(recovered_app).get("/api/v2/qx/opportunities")
    assert recovered.status_code == 200
    assert recovered.json()["source_mode"] == "LIVE"


def test_detail_api_passes_the_server_environment_boundary(tmp_path, monkeypatch) -> None:
    database = tmp_path / "runtime.db"
    repository = OpportunityRepository(database)
    seen = []

    def get_detail(evaluation_id, *, environment_id):
        seen.append((evaluation_id, environment_id))
        return None

    monkeypatch.setattr(repository, "get_detail", get_detail)
    app = FastAPI()
    app.include_router(create_opportunity_router(repository, environment_id="production"))
    evaluation_id = "qxev1_00000000000070008000000000000001"
    response = TestClient(app).get(f"/api/v2/qx/opportunities/{evaluation_id}")
    assert response.status_code == 404
    assert seen == [(evaluation_id, "production")]


def test_interactive_evaluation_does_not_publish_live_opportunity(
    tmp_path,
    monkeypatch,
) -> None:
    database = tmp_path / "runtime.db"
    OpportunityRepository(database)
    monkeypatch.setattr(
        qx_v2,
        "load_pipeline_bars",
        lambda *args, **kwargs: (None, 0.0, 0, 1),
    )

    def evaluate(context, config):
        return QXEvaluationResult(
            symbol=context.symbol,
            timeframe=context.timeframe,
            evaluation_timestamp=context.evaluation_timestamp,
            request_started_at=context.request_started_at,
            publication_state=PublicationState.RESEARCH_ONLY,
            current_lifecycle_state=LifecycleState.NO_SETUP,
            evidence_summary=[],
            reason_codes=["NO_SETUP"],
            config_version=config.version,
            pipeline_version="core_v1",
            data_dependencies=context.data_dependencies,
            io_metrics=context.io_metrics,
        )

    monkeypatch.setattr(qx_v2.orchestrator, "run_pipeline", evaluate)
    app = create_app(
        database=database,
        cache_dir=tmp_path / "bars",
        configure_canonical_providers=False,
    )
    response = TestClient(app).post("/api/v2/qx/evaluate/SPY")
    assert response.status_code == 200
    assert response.json()["publication_state"] == "RESEARCH_ONLY"
    with sqlite3.connect(database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM opportunity_evaluations").fetchone()[0]
    assert count == 0
