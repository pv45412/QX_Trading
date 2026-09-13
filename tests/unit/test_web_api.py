import json
import sqlite3

import pytest
from fastapi import HTTPException

from qx.interfaces.web import create_app
from qx.interfaces.web import snapshot_age
from datetime import datetime, timezone


def read_snapshot(path):
    app = create_app(path)
    return next(route.endpoint for route in app.routes if route.path == "/api/rotation")()


@pytest.mark.parametrize("timestamp,status,seconds", [
    ("2026-09-09T12:00:00+00:00", "RECENT", 0),
    ("2026-09-08T12:00:00+00:00", "OLD", 86400),
    ("2026-09-09T08:00:00-04:00", "RECENT", 0),
    ("2026-09-10T12:00:00+00:00", "UNKNOWN", None),
    ("2026-09-09T12:00:00", "UNKNOWN", None),
    ("invalid", "UNKNOWN", None), (None, "UNKNOWN", None),
])
def test_snapshot_age_does_not_imply_market_freshness(timestamp, status, seconds):
    result = snapshot_age(timestamp, datetime(2026, 9, 9, 12, tzinfo=timezone.utc))
    assert result == {"age_seconds": seconds, "age_status": status}


def test_missing_database_is_empty_and_not_created(tmp_path):
    path = tmp_path / "missing.db"
    assert read_snapshot(path) == {"snapshot": None, "rows": []}
    assert not path.exists()


def test_snapshot_projection_excludes_internal_fields(tmp_path):
    path = tmp_path / "test.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE sector_rotation_snapshots(id INTEGER, created_at TEXT, data_source TEXT, payload_json TEXT)")
        conn.execute("INSERT INTO sector_rotation_snapshots VALUES(1, '2026-09-09', 'schwab', ?)",
                     (json.dumps({"benchmark": "SPY", "sectors": [{"etf": "XLK", "sector": "Technology", "private": "not exposed", "relative_20d": .1}]}),))
    result = read_snapshot(path)
    assert result["rows"][0]["relative_20d"] == .1
    assert "private" not in result["rows"][0]
    assert result["snapshot"]["requested_source"] == "schwab"


def test_corrupt_database_returns_sanitized_error(tmp_path):
    path = tmp_path / "broken.db"
    path.write_bytes(b"not sqlite")
    with pytest.raises(HTTPException) as error:
        read_snapshot(path)
    assert error.value.status_code == 503
    assert str(path) not in error.value.detail


@pytest.mark.parametrize("key,value", [
    ("etf", None), ("sector", {}), ("relative_20d", True),
    ("relative_5d", "0.1"), ("rs_quadrant", {}), ("rs_status", []),
    ("relative_60d", float("inf")),
])
def test_invalid_row_fields_fail_closed(tmp_path, key, value):
    path = tmp_path / "invalid.db"
    item = {"etf": "XLK", "sector": "Technology", key: value}
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE sector_rotation_snapshots(id INTEGER, created_at TEXT, data_source TEXT, payload_json TEXT)")
        conn.execute("INSERT INTO sector_rotation_snapshots VALUES(1, '2026-09-09', 'schwab', ?)",
                     (json.dumps({"benchmark": "SPY", "sectors": [item]}),))
    with pytest.raises(HTTPException) as error:
        read_snapshot(path)
    assert error.value.status_code == 503
