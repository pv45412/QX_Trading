from pathlib import Path
from hashlib import sha256
from io import BytesIO
import json
import os
import tempfile

import pandas as pd

from qx.data.providers import REQUIRED_COLUMNS, MarketDataProvider, normalize_ohlcv
from qx.models.market import BarDataRequest, IntradayBarDataRequest
from qx.data.provenance import tag_bars, valid_provenance


class CachedMarketDataProvider:
    """Caches normalized OHLCV data per symbol and period."""

    def __init__(
        self,
        provider: MarketDataProvider,
        cache_dir: Path = Path("data/cache/bars"),
        refresh: bool = False,
    ) -> None:
        self.provider = provider
        self.cache_dir = cache_dir
        self.refresh = refresh

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        cache_path = self.cache_dir / f"{_cache_symbol(request.symbol)}_{request.period}.csv"
        if cache_path.exists() and not self.refresh:
            return _read_cached_bars(cache_path)

        bars = self.provider.get_daily_bars(request)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return _write_cached_bars(cache_path, bars, self.provider)

    def get_intraday_bars(self, request: IntradayBarDataRequest) -> pd.DataFrame:
        interval = f"{request.interval_minutes}m"
        cache_path = self.cache_dir / "intraday" / f"{_cache_symbol(request.symbol)}_{request.period}_{interval}.csv"
        if cache_path.exists() and not self.refresh:
            return _read_cached_bars(cache_path)

        bars = self.provider.get_intraday_bars(request)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        return _write_cached_bars(cache_path, bars, self.provider)


def _cache_symbol(symbol: str) -> str:
    return (
        symbol.upper()
        .replace("/", "_")
        .replace("\\", "_")
        .replace("=", "_")
        .replace("^", "_")
        .replace(".", "_")
    )


def _read_cached_bars(cache_path: Path) -> pd.DataFrame:
    content = cache_path.read_bytes()
    bars = _parse_cached_bars(content)
    provenance = {"schema_version": 1, "actual_source": "unknown", "retrieved_at": None,
                  "last_bar_label": None, "fallback_used": None}
    try:
        metadata = json.loads(cache_path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        if (isinstance(metadata, dict) and metadata.get("sha256") == sha256(content).hexdigest()
                and valid_provenance(metadata.get("provenance"))):
            provenance = metadata["provenance"]
    except (OSError, ValueError):
        pass
    bars.attrs["provenance"] = provenance
    return bars


def _atomic_write(path: Path, content: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_cached_bars(path: Path, bars: pd.DataFrame, provider: object) -> pd.DataFrame:
    result = bars if "provenance" in bars.attrs else tag_bars(bars, provider)
    content = result.to_csv().encode("utf-8")
    metadata = {"sha256": sha256(content).hexdigest(), "provenance": result.attrs["provenance"]}
    # An interrupted/interleaved pair fails its digest check instead of misattributing data.
    _atomic_write(path, content)
    _atomic_write(path.with_suffix(".meta.json"), json.dumps(metadata).encode("utf-8"))
    return result


def _parse_cached_bars(content: bytes) -> pd.DataFrame:
    frame = pd.read_csv(BytesIO(content))
    first_column = frame.columns[0]
    first_column_name = str(first_column).strip().lower()
    if first_column_name in {"date", "datetime"} or first_column_name.startswith("unnamed"):
        parsed_dates = pd.to_datetime(frame[first_column], errors="coerce")
        if parsed_dates.notna().any():
            frame = frame.drop(columns=[first_column])
            frame.index = parsed_dates

    normalized_columns = [str(column).strip().lower().replace(" ", "_") for column in frame.columns]
    if set(REQUIRED_COLUMNS).issubset(normalized_columns):
        return normalize_ohlcv(frame)

    parsed_dates = pd.to_datetime(frame[first_column], errors="coerce")
    if parsed_dates.notna().any():
        frame = frame.drop(columns=[first_column])
        frame.index = parsed_dates
    return normalize_ohlcv(frame)
