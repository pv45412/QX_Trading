"""Refresh coordination with process-local progress and cross-process writer exclusion."""
from collections.abc import Callable
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Any
from uuid import uuid4

import pandas as pd

from qx.data.cache import _atomic_write, _write_cached_bars
from qx.data.provenance import valid_provenance
from qx.data.providers import MarketDataProvider
from qx.market.dashboard_metrics import DASHBOARD_ETFS, metrics
from qx.market.movers import _validate_bars
from qx.market.sessions import IncompleteSessionWindow, _schedule, completed_mover_bars
from qx.models.market import BarDataRequest


class RefreshLockUnavailable(RuntimeError):
    """The refresh cannot safely acquire its publication lease."""


def _publication_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError("Duplicate refresh publication fields")
        fields[key] = value
    return fields


def _validate_publication_dates(finished: str, session: str, now: datetime) -> None:
    timestamp, day = datetime.fromisoformat(finished), date.fromisoformat(session)
    if timestamp.utcoffset() is None or timestamp > now or day.isoformat() != session:
        raise ValueError("Invalid refresh publication dates")
    try:
        schedule = _schedule(day)
        if schedule.empty or schedule.index[-1].date() != day:
            raise ValueError("Publication date is not an equity session")
        available_at = schedule.iloc[-1]["market_close"] + pd.Timedelta(minutes=30)
        if pd.Timestamp(timestamp) < available_at:
            raise ValueError("Publication precedes the completed-session availability time")
    except Exception as exc:
        raise ValueError("Refresh publication session could not be verified") from exc


def _completed_refresh_bars(bars: pd.DataFrame, now: datetime) -> pd.DataFrame:
    _validate_bars(bars)
    index = pd.DatetimeIndex(bars.index)
    if not index.equals(index.normalize()):
        raise ValueError("Daily refresh requires unambiguous midnight session labels")
    provenance = bars.attrs.get("provenance")
    if (isinstance(provenance, dict) and valid_provenance(provenance)
            and provenance["last_bar_label"] != index[-1].isoformat()):
        raise ValueError("Incoming provenance does not match its daily labels")
    result = completed_mover_bars(bars, now, required_sessions=22)
    # Midnight daily labels keep their calendar date; never relabel intraday instants.
    result.index = pd.DatetimeIndex(result.index).tz_localize(None)
    if isinstance(provenance, dict) and valid_provenance(provenance):
        result.attrs["provenance"] = {**provenance, "last_bar_label": result.index[-1].isoformat()}
    return result


class DashboardRefresh:
    def __init__(self, cache: Path, provider: Callable[[], MarketDataProvider]) -> None:
        self.cache = cache
        self.root = cache.parent / "dashboard_refresh"
        self.provider = provider
        self.lock = Lock()
        self.initial_total = 32
        self.state: dict[str, Any] = {"status": "idle", "completed": 0, "total": self.initial_total}
        self._reservation: sqlite3.Connection | None = None
        self._executing = False

    def active_cache(self) -> Path:
        document = self._publication()
        return self.cache if document is None else self.root / document["generation"]

    def _publication(self) -> dict[str, str] | None:
        try:
            content = (self.root / "current.json").read_text()
        except FileNotFoundError:
            return None
        document = json.loads(content, object_pairs_hook=_publication_fields)
        if not isinstance(document, dict):
            raise ValueError("Invalid refresh publication")
        generation = document["generation"]
        if not isinstance(generation, str) or len(generation) != 32 or any(c not in "0123456789abcdef" for c in generation):
            raise ValueError("Invalid dashboard generation")
        finished, session = document["finished_at"], document["data_as_of"]
        if not isinstance(finished, str) or not isinstance(session, str):
            raise ValueError("Invalid refresh publication dates")
        _validate_publication_dates(finished, session, datetime.now(timezone.utc))
        destination = self.root / generation
        if not destination.is_dir() or destination.resolve().parent != self.root.resolve():
            raise ValueError("Published refresh folder unavailable")
        # This validates the pointer, not the generation's market evidence or freshness.
        return {"generation": generation, "finished_at": finished, "data_as_of": session}

    def status(self) -> dict[str, Any]:
        with self.lock:
            result = dict(self.state)
        try:
            saved = self._publication()
            if saved is not None:
                result.update(last_success=saved["finished_at"], data_as_of=saved["data_as_of"])
        except (OSError, ValueError, KeyError, TypeError):
            result["storage_warning"] = "Saved refresh metadata or published folder unavailable. Refresh explicitly to rebuild."
        return result

    def reserve(self) -> bool:
        with self.lock:
            return self._reserve_locked()

    def _reserve_locked(self) -> bool:
        if self._reservation is not None:
            return False
        connection = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.root / "refresh-lock.sqlite", timeout=0,
                                         isolation_level=None, check_same_thread=False)
            # A dedicated transaction is an OS-released lease, not the scan-history DB.
            connection.execute("BEGIN IMMEDIATE")
        except (sqlite3.Error, OSError) as exc:
            if connection is not None:
                connection.close()
            if getattr(exc, "sqlite_errorcode", 0) & 0xFF not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                self.state.update(status="failed", error="Refresh lock unavailable. No work started.")
                raise RefreshLockUnavailable("Refresh lock unavailable. No work started.") from None
            return False
        self._reservation = connection
        self.state = {"status": "running", "completed": 0, "total": self.initial_total}
        return True

    def _begin_run(self) -> bool:
        with self.lock:
            if self._executing:
                return False
            if self._reservation is None:
                try:
                    if not self._reserve_locked():
                        return False
                except RefreshLockUnavailable:
                    return False
            self._executing = True
            return True

    def _release_run(self) -> None:
        with self.lock:
            try:
                if self._reservation is not None:
                    self._reservation.close()
            finally:
                self._reservation = None
                self._executing = False

    def _record_session_failure(self, symbol: str, exc: IncompleteSessionWindow) -> None:
        last = exc.last_available.isoformat() if exc.last_available else None
        with self.lock:
            self.state.update(
                status="failed", error_code="incomplete_sessions", failed_symbol=symbol,
                expected_session=exc.expected.isoformat(), last_available_session=last,
                required_sessions=exc.required,
                error=(f"{symbol}: requires {exc.required} completed NYSE sessions through {exc.expected}; "
                       f"last available daily label {last or 'unavailable'}. Previous data retained."),
            )

    def run(self, now: datetime | None = None) -> None:
        if not self._begin_run():
            return
        now = now or datetime.now(timezone.utc)
        try:
            provider = self.provider()
            symbols = list(dict.fromkeys(["SPY", "QQQ", "DIA", *DASHBOARD_ETFS.values()]))
            frames = {}
            for symbol in symbols:
                bars = provider.get_daily_bars(BarDataRequest(symbol=symbol, period="1y"))
                try:
                    frames[symbol] = _completed_refresh_bars(bars, now)
                except IncompleteSessionWindow as exc:
                    self._record_session_failure(symbol, exc)
                    return
                with self.lock:
                    self.state["completed"] = len(frames)
            for symbol in symbols:
                metrics(frames[symbol], frames["SPY"])
            generation = uuid4().hex
            destination = self.root / generation
            destination.mkdir(parents=True)
            for symbol, bars in frames.items():
                _write_cached_bars(destination / f"{symbol}_1y.csv", bars, provider)
            saved = {"generation": generation, "finished_at": datetime.now(timezone.utc).isoformat(),
                     "data_as_of": frames["SPY"].index[-1].date().isoformat()}
            _atomic_write(self.root / "current.json", json.dumps(saved).encode())
            with self.lock:
                self.state["status"] = "succeeded"
        except Exception:
            # Provider exceptions may contain sensitive request details.
            with self.lock:
                self.state.update(status="failed", error="Refresh failed validation or provider access. Previous data retained.")
        finally:
            self._release_run()
