"""Inspection-only stock evidence from one published, membership-bound generation."""

import csv
from datetime import date, datetime, timezone
from hashlib import sha256
from io import StringIO
import json
import math
from pathlib import Path
import re
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from qx.data.cache import _cache_symbol
from qx.data.membership import membership_source, membership_symbols
from qx.data.provenance import valid_provenance
from qx.market.ai_review import (
    METRIC_FIELDS, TTL, ReviewUnavailable, _aware, _calendar, _completed, _identity,
    _unique_object,
)
from qx.market.dashboard_metrics import DASHBOARD_ETFS, metrics

STOCK_SCHEMA_VERSION = "qx.stock-evidence.v1"
StockUniverse = Literal["sp500", "sp100", "nasdaq_100", "dow_jones"]
STOCK_UNIVERSES = ("sp500", "sp100", "nasdaq_100", "dow_jones")
OHLCV = ("open", "high", "low", "close", "volume")
LIMITATIONS = [
    "Inspection only. Stock AI output generation has no supported contract.",
    "Frozen local membership is not certified index membership; official membership and effective date are unknown.",
    "Metrics use exactly 22 aligned completed NYSE daily observations from one stock-refresh generation; no rows are repaired or replaced.",
    "Source attribution and file integrity are not independent price or corporate-action adjustment certification.",
    "Only the selected stock and SPY are inspected; no whole-universe coverage, rank or official instrument classification is certified.",
    "No live quotes, earnings calendar, fundamentals, options, futures, trade instructions, sizing or predictive probability.",
]


class UnsupportedStockEvidence(ReviewUnavailable):
    pass


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class StockPublication(_Contract):
    generation: str = Field(pattern=r"^[a-f0-9]{32}$")
    finished_at: str
    data_as_of: str


class StockMembership(_Contract):
    symbols: list[str] = Field(default_factory=list)
    selected_symbol_present: bool = False
    provenance_status: Literal["unknown", "content_bound"] = "unknown"
    source: str = "unknown"
    retrieved_at: str | None = None
    official_membership: Literal["unknown"] = "unknown"
    official: Literal[False] = False
    effective_date: None = None


class StockBarSource(_Contract):
    schema_version: int | None = None
    actual_source: str = "unknown"
    fallback_used: bool | None = None
    retrieved_at: str | None = None
    last_bar_label: str | None = None
    provenance_verified: bool = False


class StockBarWindow(_Contract):
    dates: list[str] = Field(default_factory=list)
    open: list[float] = Field(default_factory=list)
    high: list[float] = Field(default_factory=list)
    low: list[float] = Field(default_factory=list)
    close: list[float] = Field(default_factory=list)
    volume: list[float] = Field(default_factory=list)


class StockFacts(_Contract):
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,11}$")
    benchmark: Literal["SPY"] = "SPY"
    universe: StockUniverse
    publication: StockPublication | None = None
    membership: StockMembership = Field(default_factory=StockMembership)
    input_digests: dict[str, str | None] = Field(default_factory=dict)
    sources: dict[str, StockBarSource] = Field(default_factory=dict)
    windows: dict[str, StockBarWindow] = Field(default_factory=dict)
    bar_date: str | None = None
    return_1d: float | None = None
    excess_1d: float | None = None
    rs_change: float | None = None
    rs_days: int | None = None
    up_days: int | None = None
    down_days: int | None = None
    days_off_high: int | None = None


class StockValidation(_Contract):
    price_status: Literal["unavailable", "unverified", "historical", "verified_completed_daily"] = Field(
        description="Selected stock/SPY price evidence only; never official membership or permission to generate AI output.")
    live_eligible: Literal[False] = False
    generation_supported: Literal[False] = False
    issues: list[str]


class StockEvidence(_Contract):
    schema_version: Literal["qx.stock-evidence.v1"]
    mode: Literal["inspection_only"]
    snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    checked_at: str
    expires_at: str
    facts: StockFacts
    validation: StockValidation
    limitations: list[str]


class _Inputs:
    """Capture bytes once, then check publication and every input for read races."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.content: dict[Path, bytes | None] = {}

    def read(self, path: Path) -> bytes | None:
        if path.resolve().parent != path.parent.resolve() or path.is_symlink():
            raise ValueError("Input escapes its generation")
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            content = None
        self.content[path] = content
        return content

    def digests(self) -> dict[str, str | None]:
        return {path.relative_to(self.root).as_posix(): sha256(content).hexdigest() if content is not None else None
                for path, content in self.content.items()}

    def require_unchanged(self) -> None:
        try:
            for path, content in list(self.content.items()):
                if self.read(path) != content:
                    raise ValueError("Changed bytes")
        except (OSError, ValueError) as exc:
            raise ReviewUnavailable("Stock evidence changed during inspection; reload local evidence.") from exc


def _document(content: bytes | None) -> dict[str, Any]:
    if content is None:
        raise ValueError("Missing metadata")
    value = json.loads(content, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("Invalid metadata object")
    return value


def _rows(content: bytes | None) -> list[list[str]]:
    if content is None:
        raise ValueError("Missing CSV")
    rows = list(csv.reader(StringIO(content.decode("utf-8-sig")), strict=True))
    if (not rows or len(rows[0]) != len(set(rows[0]))
            or any(len(row) != len(rows[0]) for row in rows[1:])):
        raise ValueError("Invalid raw CSV shape")
    return rows


def _publication(inputs: _Inputs, now: datetime) -> tuple[StockPublication, Path]:
    record = StockPublication.model_validate(_document(inputs.read(inputs.root / "current.json")))
    session = date.fromisoformat(record.data_as_of)
    schedule = _calendar(session)
    if (session.isoformat() != record.data_as_of or schedule.index[-1].date() != session
            or not schedule.iloc[-1]["market_close"] + pd.Timedelta(minutes=30)
            <= _aware(record.finished_at) <= now):
        raise ValueError("Invalid publication dates")
    directory = inputs.root / record.generation
    if not directory.is_dir() or directory.resolve().parent != inputs.root.resolve():
        raise ValueError("Invalid published directory")
    return record, directory


def _membership(inputs: _Inputs, directory: Path, symbol: str,
                publication: StockPublication) -> StockMembership:
    content = inputs.read(directory / "symbols.csv")
    metadata = inputs.read(directory / "symbols.meta.json")
    _rows(content)
    if content is None:
        raise ValueError("Missing frozen membership")
    symbols = membership_symbols(content)
    if len({_cache_symbol(item) for item in ["SPY", *symbols]}) != len(symbols) + 1:
        raise ValueError("Ambiguous stock/benchmark identity")
    result = StockMembership(symbols=symbols, selected_symbol_present=symbol in symbols)
    try:
        if metadata is None:
            raise ValueError("Missing membership provenance")
        source, retrieved = membership_source(content, metadata, as_of=_aware(publication.finished_at))
        result.provenance_status = "content_bound"
        result.source = source
        result.retrieved_at = retrieved.isoformat()
    except (ValueError, KeyError, TypeError, OverflowError):
        pass
    # Neither sidecar claims nor local list inclusion establish official membership.
    return result


def _bars(content: bytes | None, publication: StockPublication) -> tuple[StockBarWindow, pd.DataFrame]:
    rows = _rows(content)
    header = rows[0]
    if len(rows) != 23 or not set(OHLCV) <= set(header[1:]):
        raise ValueError("Exactly 22 raw OHLCV bars required")
    dates = pd.DatetimeIndex(pd.to_datetime([row[0] for row in rows[1:]], errors="raise"))
    expected = _calendar(date.fromisoformat(publication.data_as_of)).index[-22:]
    if dates.tz is not None or not dates.equals(expected):
        raise ValueError("Raw bars do not match the completed publication sessions")
    values = {key: [float(row[header.index(key)]) for row in rows[1:]] for key in OHLCV}
    for key, numbers in values.items():
        if any(not math.isfinite(value) or value < 0 or (key != "volume" and value == 0) for value in numbers):
            raise ValueError("Invalid raw numeric bars")
    frame = pd.DataFrame(values, index=dates)
    if ((frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any()
            or (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any()):
        raise ValueError("Inconsistent raw OHLC range")
    return StockBarWindow(dates=list(dates.strftime("%Y-%m-%d")), **values), frame


def _source(content: bytes | None, metadata: bytes | None,
            publication: StockPublication) -> StockBarSource:
    result = StockBarSource()
    try:
        record = _document(metadata)
        provenance = record["provenance"]
        if not valid_provenance(provenance):
            return result
        result = StockBarSource(**{key: provenance[key] for key in (
            "schema_version", "actual_source", "fallback_used", "retrieved_at", "last_bar_label")})
        finalized = _calendar(date.fromisoformat(publication.data_as_of)).iloc[-1]["market_close"] + pd.Timedelta(minutes=30)
        result.provenance_verified = (
            content is not None and record["sha256"] == sha256(content).hexdigest()
            and result.actual_source in {"schwab", "yfinance"}
            and result.last_bar_label == publication.data_as_of + "T00:00:00"
            and finalized <= _aware(result.retrieved_at) <= _aware(publication.finished_at)
        )
    except (ValueError, KeyError, TypeError, OverflowError):
        pass
    return result


def _snapshot_id(evidence: dict[str, Any]) -> str:
    return _identity({key: value for key, value in evidence.items()
                      if key not in {"snapshot_id", "checked_at", "expires_at"}})


def inspect_stock_evidence(symbol: str, universe: str, cache: Path,
                           now: datetime | None = None) -> dict[str, Any]:
    """Never refresh or read the mutable membership/bar fallback. No provider access."""
    now = now or datetime.now(timezone.utc)
    if (now.utcoffset() is None or universe not in STOCK_UNIVERSES
            or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,11}", symbol)
            or symbol in {*DASHBOARD_ETFS.values(), "SPY", "QQQ", "DIA"}):
        raise UnsupportedStockEvidence("Unsupported stock symbol, universe or inspection clock; futures/options require separate contracts.")
    facts = StockFacts.model_validate({"symbol": symbol, "universe": universe})
    inputs = _Inputs(cache.parent / "stock_refresh" / universe)
    issues: list[str] = []
    status = "unavailable"
    try:
        publication, directory = _publication(inputs, now)
        facts.publication = publication
        facts.membership = _membership(inputs, directory, symbol, publication)
        if not facts.membership.selected_symbol_present:
            raise ValueError("Selected symbol absent from frozen membership")
        frames = {}
        for ticker in (symbol, "SPY"):
            path = directory / f"{_cache_symbol(ticker)}_1y.csv"
            content, metadata = inputs.read(path), inputs.read(path.with_suffix(".meta.json"))
            facts.sources[ticker] = _source(content, metadata, publication)
            try:
                facts.windows[ticker], frames[ticker] = _bars(content, publication)
            except (ValueError, TypeError, KeyError, IndexError, OverflowError, csv.Error):
                issues.append(f"{ticker}: invalid or incomplete raw OHLCV/session evidence; no replacement used.")
            if not facts.sources[ticker].provenance_verified:
                issues.append(f"{ticker}: source attribution, digest or retrieval/bar timestamp unverified.")
        if len(frames) == 2:
            values = metrics(frames[symbol], frames["SPY"])
            facts = StockFacts.model_validate({**facts.model_dump(), **{key: values[key] for key in METRIC_FIELDS},
                                               "bar_date": publication.data_as_of})
            status = "unverified" if issues else "verified_completed_daily"
            if list(frames["SPY"].index) != list(_completed(now).index[-22:]):
                issues.append("Historical window: not the latest 22 completed NYSE sessions.")
                if status == "verified_completed_daily":
                    status = "historical"
    except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError, csv.Error):
        issues.append("Published stock generation, frozen membership or aligned complete raw bars unavailable; no fallback used.")
    inputs.require_unchanged()
    facts.input_digests = inputs.digests()
    if facts.membership.provenance_status == "unknown":
        issues.append("Frozen membership retrieval provenance unknown; local inclusion is not official membership.")
    evidence = {"schema_version": STOCK_SCHEMA_VERSION, "mode": "inspection_only",
                "checked_at": now.isoformat(), "expires_at": (now + TTL).isoformat(),
                "facts": facts.model_dump(),
                "validation": {"price_status": status, "live_eligible": False,
                               "generation_supported": False, "issues": issues},
                "limitations": list(LIMITATIONS)}
    evidence["snapshot_id"] = _snapshot_id(evidence)
    return StockEvidence.model_validate(evidence).model_dump()


def validate_stock_evidence(evidence: Any, cache: Path, now: datetime | None = None) -> None:
    """Rebuild from local bytes: an ID, rehash or caller's flags are not a trust boundary."""
    now = now or datetime.now(timezone.utc)
    try:
        contract = StockEvidence.model_validate(evidence)
        checked, expires = _aware(contract.checked_at), _aware(contract.expires_at)
        if not checked <= now < expires or expires - checked != TTL:
            raise ValueError("Invalid inspection lease")
        rebuilt = inspect_stock_evidence(contract.facts.symbol, contract.facts.universe, cache, checked)
        if _identity(evidence) != _identity(rebuilt):
            raise ValueError("Changed evidence or invalid assertions")
        current = inspect_stock_evidence(contract.facts.symbol, contract.facts.universe, cache, now)
        if current["snapshot_id"] != contract.snapshot_id:
            raise ValueError("Changed evidence or session rollover")
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError) as exc:
        raise ReviewUnavailable("Invalid or expired stock inspection; reload local evidence. Stock generation is unsupported.") from exc
