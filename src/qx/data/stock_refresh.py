"""Isolated, all-or-nothing price refresh for a cached constituent universe."""
from datetime import datetime, timezone
from collections.abc import Callable
from pathlib import Path
import json
from uuid import uuid4

from qx.data.cache import _atomic_write, _cache_symbol, _write_cached_bars
from qx.data.dashboard_refresh import DashboardRefresh, _completed_refresh_bars
from qx.data.membership import membership_symbols
from qx.data.providers import MarketDataProvider
from qx.market.dashboard_metrics import closes
from qx.market.sessions import IncompleteSessionWindow
from qx.models.market import BarDataRequest


class StockRefresh(DashboardRefresh):
    def __init__(self, cache: Path, provider: Callable[[], MarketDataProvider], universe: str) -> None:
        super().__init__(cache, provider)
        if universe not in {"sp500", "sp100", "nasdaq_100", "dow_jones"}:
            raise ValueError("Unsupported universe")
        self.universe = universe
        self.root = cache.parent / "stock_refresh" / universe
        self.initial_total = 0
        self.state["total"] = 0

    def run(self, now: datetime | None = None) -> None:
        if not self._begin_run():
            return
        now = now or datetime.now(timezone.utc)
        try:
            membership = self.cache.parent / f"{self.universe}_symbols.csv"
            content = membership.read_bytes()
            sidecar = membership.with_suffix(".meta.json")
            metadata = _optional_bytes(sidecar)
            symbols = membership_symbols(content)
            requests = list(dict.fromkeys(["SPY", *symbols]))
            if len({_cache_symbol(s) for s in requests}) != len(requests):
                raise ValueError("Ambiguous cache symbol identity")
            with self.lock:
                self.state.update(total=len(requests), completed=0)
            provider = self.provider()
            destination = self.root / uuid4().hex
            destination.mkdir(parents=True)
            reference = None
            for index, symbol in enumerate(requests):
                bars = provider.get_daily_bars(BarDataRequest(symbol=symbol, period="1y"))
                try:
                    bars = _completed_refresh_bars(bars, now).tail(22)
                except IncompleteSessionWindow as exc:
                    self._record_session_failure(symbol, exc)
                    return
                closes(bars)
                if reference is None:
                    reference = bars.index
                elif not reference.equals(bars.index):
                    raise ValueError("Unmatched sessions")
                _write_cached_bars(destination / f"{_cache_symbol(symbol)}_1y.csv", bars, provider)
                with self.lock:
                    self.state["completed"] = index + 1
            _atomic_write(destination / "symbols.csv", content)
            if metadata is not None:
                _atomic_write(destination / "symbols.meta.json", metadata)
            if membership.read_bytes() != content or _optional_bytes(sidecar) != metadata:
                raise ValueError("Membership or its provenance changed during refresh")
            saved = {"generation": destination.name, "finished_at": datetime.now(timezone.utc).isoformat(),
                     "data_as_of": reference[-1].date().isoformat() if reference is not None else None}
            _atomic_write(self.root / "current.json", json.dumps(saved).encode())
            with self.lock:
                self.state["status"] = "succeeded"
        except Exception:
            with self.lock:
                self.state.update(status="failed", error="Stock refresh failed validation or provider access. Previous generation retained.")
        finally:
            self._release_run()


def _optional_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
