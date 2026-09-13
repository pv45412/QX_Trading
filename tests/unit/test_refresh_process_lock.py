from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
from threading import Event
from types import SimpleNamespace

from fastapi import BackgroundTasks, HTTPException, Request
import pandas as pd
import pandas_market_calendars as mcal
import pytest

from qx.data.dashboard_refresh import DashboardRefresh, RefreshLockUnavailable
from qx.data.stock_refresh import StockRefresh
from qx.interfaces.web import create_app


def unavailable_provider():
    raise RuntimeError("sensitive provider detail")


@pytest.mark.parametrize("stock", [False, True])
def test_independent_coordinators_share_exclusion_and_release_after_failure(tmp_path, stock):
    def coordinator():
        return StockRefresh(tmp_path / "bars", unavailable_provider, "sp100") if stock else DashboardRefresh(tmp_path / "bars", unavailable_provider)

    first, second = coordinator(), coordinator()
    assert first.reserve()
    assert not second.reserve()
    first.run()
    assert first.status()["status"] == "failed"
    assert "sensitive" not in str(first.status())
    assert second.reserve()
    second.run()
    assert second.status()["status"] == "failed"


def test_direct_run_does_not_bypass_another_worker_reservation(tmp_path):
    calls = []
    first = DashboardRefresh(tmp_path / "bars", unavailable_provider)
    second = DashboardRefresh(tmp_path / "bars", lambda: calls.append(True))
    assert first.reserve()
    second.run()
    assert calls == []
    first.run()
    second.run()
    assert calls == [True]


def test_duplicate_run_cannot_release_an_executing_workers_lease(tmp_path):
    entered, finish = Event(), Event()
    calls = []

    def provider():
        calls.append(True)
        entered.set()
        if not finish.wait(10):
            raise TimeoutError("test timed out")
        raise RuntimeError("fixture failure")

    first = DashboardRefresh(tmp_path / "bars", provider)
    competitor = DashboardRefresh(tmp_path / "bars", unavailable_provider)
    assert first.reserve()
    with ThreadPoolExecutor(max_workers=1) as executor:
        worker = executor.submit(first.run)
        try:
            assert entered.wait(10)
            first.run()
            assert calls == [True]
            assert not competitor.reserve()
        finally:
            finish.set()
            worker.result(timeout=10)
    assert competitor.reserve()
    competitor.run()


def test_reservation_and_execution_can_run_on_different_threads(tmp_path):
    coordinator = DashboardRefresh(tmp_path / "bars", unavailable_provider)
    assert coordinator.reserve()
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(coordinator.run).result(timeout=10)
    assert coordinator.status()["status"] == "failed"
    assert coordinator.reserve()
    coordinator.run()


def test_unrelated_refresh_targets_do_not_block_each_other(tmp_path):
    coordinators = [DashboardRefresh(tmp_path / "bars", unavailable_provider),
                    StockRefresh(tmp_path / "bars", unavailable_provider, "sp100"),
                    StockRefresh(tmp_path / "bars", unavailable_provider, "sp500")]
    try:
        assert all(item.reserve() for item in coordinators)
    finally:
        for item in coordinators:
            item.run()


def test_status_reads_do_not_create_lock_storage(tmp_path):
    coordinator = DashboardRefresh(tmp_path / "bars", unavailable_provider)
    assert coordinator.status()["status"] == "idle"
    assert coordinator.active_cache() == tmp_path / "bars"
    assert not list(tmp_path.iterdir())


def test_crashed_process_releases_lease_without_deleting_lock_file(tmp_path):
    source = Path(__file__).resolve().parents[2] / "src"
    environment = {**os.environ, "PYTHONPATH": str(source)}
    code = (
        "import sys; from pathlib import Path; "
        "from qx.data.dashboard_refresh import DashboardRefresh; "
        "c=DashboardRefresh(Path(sys.argv[1]),lambda:None); "
        "assert c.reserve(); print('reserved',flush=True); sys.stdin.readline()"
    )
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    child = subprocess.Popen([sys.executable, "-c", code, str(tmp_path / "bars")],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, env=environment, creationflags=flags)
    coordinator = DashboardRefresh(tmp_path / "bars", unavailable_provider)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            line = executor.submit(child.stdout.readline)
            try:
                assert line.result(timeout=15).strip() == "reserved"
            except BaseException:
                child.kill()
                raise
        assert not coordinator.reserve()
        child.kill()
        child.communicate(timeout=10)
        assert (coordinator.root / "refresh-lock.sqlite").exists()
        assert coordinator.reserve()
        coordinator.run()
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)


def test_storage_failure_blocks_work_and_is_not_reported_as_busy(tmp_path):
    calls = []
    coordinator = DashboardRefresh(tmp_path / "bars", lambda: calls.append(True))
    coordinator.root.write_text("not a directory")
    with pytest.raises(RefreshLockUnavailable, match="No work started"):
        coordinator.reserve()
    coordinator.run()
    assert calls == []
    assert coordinator.status()["status"] == "failed"


@pytest.mark.parametrize("stock", [False, True])
@pytest.mark.parametrize("status_code", [409, 503])
def test_api_distinguishes_storage_failure_from_duplicate_work(tmp_path, monkeypatch, stock, status_code):
    def refuse(self):
        if status_code == 503:
            raise RefreshLockUnavailable("Refresh lock unavailable. No work started.")
        return False

    monkeypatch.setattr(DashboardRefresh, "reserve", refuse)
    app = create_app(cache_dir=tmp_path / "bars")
    path = "/api/stock-refresh/{universe}" if stock else "/api/refresh"
    endpoint = next(route.endpoint for route in app.routes if route.path == path and "POST" in route.methods)
    request = Request({"type": "http", "headers": [(b"x-qx-refresh", b"1")]})
    tasks = BackgroundTasks()
    with pytest.raises(HTTPException) as error:
        if stock:
            endpoint("sp100", request, tasks)
        else:
            endpoint(request, tasks)
    assert error.value.status_code == status_code
    assert tasks.tasks == []


@pytest.mark.parametrize("change", ["replace", "remove", "add"])
def test_membership_metadata_changes_prevent_publication_and_release_lease(tmp_path, change):
    membership = tmp_path / "sp100_symbols.csv"
    membership.write_text("symbol\nAAA\n")
    sidecar = membership.with_suffix(".meta.json")
    if change != "add":
        sidecar.write_text('{"source":"initial"}')
    dates = mcal.get_calendar("NYSE").schedule(start_date="2026-06-01", end_date="2026-09-09").index
    frame = pd.DataFrame({"open":100., "high":101., "low":99., "close":100., "volume":1e6}, index=dates)

    def get(request):
        if change == "remove":
            sidecar.unlink(missing_ok=True)
        else:
            sidecar.write_text('{"source":"changed"}')
        return frame.copy()

    provider = SimpleNamespace(get_daily_bars=lambda request: frame.copy())
    refresh = StockRefresh(tmp_path / "bars", lambda: provider, "sp100")
    now = datetime(2026, 9, 9, 22, tzinfo=timezone.utc)
    refresh.run(now)
    assert refresh.status()["status"] == "succeeded"
    published = refresh.active_cache()
    pointer = (refresh.root / "current.json").read_bytes()
    if change != "add":
        assert (published / "symbols.meta.json").read_bytes() == sidecar.read_bytes()
    else:
        assert not (published / "symbols.meta.json").exists()
    provider.get_daily_bars = get
    refresh.run(now)
    assert refresh.status()["status"] == "failed"
    assert refresh.active_cache() == published
    assert (refresh.root / "current.json").read_bytes() == pointer
    competitor = StockRefresh(tmp_path / "bars", unavailable_provider, "sp100")
    assert competitor.reserve()
    competitor.run()
