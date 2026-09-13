from datetime import datetime, timezone
import json
from types import SimpleNamespace

from fastapi import HTTPException
import pandas as pd
import pandas_market_calendars as mcal
import pytest

from qx.data.dashboard_refresh import DashboardRefresh
from qx.data.stock_refresh import StockRefresh
from qx.interfaces.web import create_app


GENERATION = "a" * 32
SAVED = {"generation": GENERATION, "finished_at": "2026-09-10T22:00:00+00:00",
         "data_as_of": "2026-09-10"}

NOW = datetime(2026, 9, 11, 14, tzinfo=timezone.utc)


@pytest.fixture
def publication_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr('qx.data.dashboard_refresh.datetime', Clock)


def coordinator(tmp_path, stock, provider=None):
    def forbidden():
        raise AssertionError("Reading publication state must not fetch data")

    factory = provider or forbidden
    return (StockRefresh(tmp_path / "bars", factory, "sp100") if stock
            else DashboardRefresh(tmp_path / "bars", factory))


def write_pointer(refresh, defect=None):
    refresh.root.mkdir(parents=True, exist_ok=True)
    destination = refresh.root / GENERATION
    if defect == "folder_is_file":
        destination.write_text("not a generation folder")
    elif defect != "missing_folder":
        destination.mkdir(exist_ok=True)
    value = dict(SAVED)
    if defect == "non_object":
        value = []
    elif defect == "no_generation":
        del value["generation"]
    elif defect == "escape":
        value["generation"] = "../sensitive-folder"
    elif defect == "numeric_generation":
        value["generation"] = 123
    elif defect == "no_finished":
        del value["finished_at"]
    elif defect == "naive_finished":
        value["finished_at"] = "2026-09-10T22:00:00"
    elif defect == "invalid_finished":
        value["finished_at"] = "sensitive-provider-detail"
    elif defect == "numeric_finished":
        value["finished_at"] = 123
    elif defect == "future_finished":
        value["finished_at"] = "2999-01-01T00:00:00Z"
    elif defect == "no_date":
        del value["data_as_of"]
    elif defect == "invalid_date":
        value["data_as_of"] = "2026-02-30"
    elif defect == "datetime_date":
        value["data_as_of"] = "2026-09-10T00:00:00"
    elif defect == "compact_date":
        value["data_as_of"] = "20260910"
    elif defect == "numeric_date":
        value["data_as_of"] = 123
    pointer = refresh.root / "current.json"
    content = "{broken" if defect == "invalid_json" else json.dumps(value)
    if defect == "duplicate_fields":
        content = '{"finished_at":"2999-01-01T00:00:00Z",' + content[1:]
    pointer.write_text(content)
    return pointer


@pytest.mark.parametrize("stock", [False, True])
@pytest.mark.parametrize("defect", ["invalid_json", "non_object", "no_generation", "escape",
    "numeric_generation", "no_finished", "naive_finished", "invalid_finished", "numeric_finished",
    "no_date", "invalid_date", "datetime_date", "compact_date", "numeric_date",
    "missing_folder", "folder_is_file"])
def test_bad_publication_is_withheld_without_fallback_or_mutation(tmp_path, stock, defect):
    refresh = coordinator(tmp_path, stock)
    pointer = write_pointer(refresh, defect)
    original = pointer.read_bytes()
    with pytest.raises((OSError, ValueError, KeyError, TypeError)):
        refresh.active_cache()
    state = refresh.status()
    assert state["storage_warning"]
    assert "last_success" not in state
    assert "data_as_of" not in state
    assert "sensitive" not in str(state)
    assert pointer.read_bytes() == original
    assert not (refresh.root / "refresh-lock.sqlite").exists()
    assert not refresh.cache.exists()


@pytest.mark.parametrize("stock", [False, True])
def test_absent_publication_uses_legacy_path_without_creating_storage(tmp_path, stock):
    refresh = coordinator(tmp_path, stock)
    assert refresh.active_cache() == refresh.cache
    assert refresh.status() == {"status": "idle", "completed": 0,
                                "total": 0 if stock else 32}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("stock", [False, True])
def test_valid_publication_is_read_only_and_does_not_certify_contents(tmp_path, stock):
    refresh = coordinator(tmp_path, stock)
    pointer = write_pointer(refresh)
    original = pointer.read_bytes()
    assert refresh.active_cache() == refresh.root / GENERATION
    state = refresh.status()
    assert state["last_success"] == SAVED["finished_at"]
    assert state["data_as_of"] == SAVED["data_as_of"]
    assert "storage_warning" not in state
    assert pointer.read_bytes() == original
    assert list((refresh.root / GENERATION).iterdir()) == []


@pytest.mark.parametrize('stock', [False, True])
@pytest.mark.parametrize('failure', ['future_finish', 'future_session', 'finish_before_close',
                                   'before_buffer', 'early_close_buffer', 'weekend', 'holiday', 'duplicate_generation',
                                   'duplicate_finished', 'duplicate_session'])
def test_temporally_invalid_or_ambiguous_publication_is_withheld(tmp_path, stock, failure, publication_clock):
    refresh = coordinator(tmp_path, stock)
    pointer = write_pointer(refresh)
    value = dict(SAVED)
    changes = {
        'future_finish': {'finished_at': '2026-09-11T14:00:01Z'},
        'future_session': {'data_as_of': '2026-09-14'},
        'finish_before_close': {'finished_at': '2026-09-10T19:59:59Z'},
        'before_buffer': {'finished_at': '2026-09-10T20:29:59Z'},
        'early_close_buffer': {'data_as_of': '2025-11-28', 'finished_at': '2025-11-28T18:29:59Z'},
        'weekend': {'data_as_of': '2026-09-06'},
        'holiday': {'data_as_of': '2026-09-07'},
    }
    content = json.dumps({**value, **changes.get(failure, {})})
    if failure.startswith('duplicate_'):
        field = {'duplicate_generation': 'generation', 'duplicate_finished': 'finished_at',
                 'duplicate_session': 'data_as_of'}[failure]
        content = '{' + json.dumps(field) + ': "conflicting", ' + content[1:]
    pointer.write_text(content)
    before = pointer.read_bytes()
    with pytest.raises(ValueError):
        refresh.active_cache()
    state = refresh.status()
    assert state['storage_warning']
    assert 'last_success' not in state
    assert 'data_as_of' not in state
    assert pointer.read_bytes() == before


@pytest.mark.parametrize('stock', [False, True])
@pytest.mark.parametrize('session,finished', [
    ('2026-09-10', '2026-09-10T20:30:00Z'),
    ('2026-09-10', '2026-09-11T14:00:00Z'),
    ('2025-11-28', '2025-11-28T18:30:00Z'),
    ('2026-01-02', '2026-01-02T16:30:00-05:00'),
])
def test_publication_accepts_completed_sessions_without_claiming_freshness(tmp_path, stock, session, finished, publication_clock):
    refresh = coordinator(tmp_path, stock)
    pointer = write_pointer(refresh)
    pointer.write_text(json.dumps({**SAVED, 'data_as_of': session, 'finished_at': finished}))
    assert refresh.active_cache() == refresh.root / GENERATION
    state = refresh.status()
    assert state['data_as_of'] == session
    assert state['last_success'] == finished
    assert 'storage_warning' not in state


@pytest.mark.parametrize("path,stock,args,code", [
    ("/api/rotation/analytics", False, (), 503),
    ("/api/rotation/{symbol}/line", False, ("XLE",), 503),
    ("/api/ai/evidence/{symbol}", False, ("XLE",), 409),
    ("/api/movers/{universe}", True, ("sp100",), 503),
])
@pytest.mark.parametrize('defect', ['missing_folder', 'future_finished', 'duplicate_fields'])
def test_invalid_publication_returns_controlled_api_error(tmp_path, monkeypatch, path, stock, args, code, defect):
    refresh = coordinator(tmp_path, stock)
    pointer = write_pointer(refresh, defect)
    original = pointer.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("No cache fallback or provider work permitted")

    monkeypatch.setattr("qx.interfaces.web._read_cached_bars", forbidden)
    monkeypatch.setattr("qx.interfaces.web.build_market_data_provider", forbidden)
    app = create_app(cache_dir=refresh.cache)
    endpoint = next(route.endpoint for route in app.routes if route.path == path)
    with pytest.raises(HTTPException) as error:
        endpoint(*args)
    assert error.value.status_code == code
    assert pointer.read_bytes() == original


@pytest.mark.parametrize("stock", [False, True])
@pytest.mark.parametrize('defect', ['missing_folder', 'future_finished', 'duplicate_fields'])
def test_explicit_refresh_recovers_bad_pointer_without_touching_legacy_cache(tmp_path, stock, defect):
    dates = mcal.get_calendar("NYSE").schedule(start_date="2026-06-01", end_date="2026-09-10").index
    bars = pd.DataFrame({"open": 100., "high": 101., "low": 99., "close": 100., "volume": 1e6}, index=dates)
    provider = SimpleNamespace(get_daily_bars=lambda request: bars.copy())
    refresh = coordinator(tmp_path, stock, lambda: provider)
    pointer = write_pointer(refresh, defect)
    if stock:
        (tmp_path / "sp100_symbols.csv").write_text("symbol\nXLE\n")
    assert refresh.status().get("storage_warning")
    refresh.run(datetime(2026, 9, 10, 22, tzinfo=timezone.utc))
    assert refresh.status()["status"] == "succeeded"
    assert "storage_warning" not in refresh.status()
    assert refresh.active_cache().name != GENERATION
    assert refresh.active_cache().is_dir()
    assert json.loads(pointer.read_text())["data_as_of"] == "2026-09-10"
    assert not refresh.cache.exists()
