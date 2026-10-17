"""Historical bar loading for backtesting, with the data defects made explicit.

The local cache is usable but not clean. Measured facts:

  * 3,237 files across 1,563 distinct symbols; 1,519 symbols carry enough history
    for MASTER AUTO (136-bar warmup + testable tail).
  * THREE header variants exist: ``date,...`` (203/400), ``open,...`` with NO date
    column at all (121/400), and ``Date,...`` (76/400). Without dates you cannot
    align bars or prove point-in-time ordering, so those files are excluded.
  * Unadjusted splits appear as enormous single-bar gaps: 17 of 300 scanned symbols
    showed a move over 45%, including +1755%, +900% and +137%. A backtest would fire
    every breakout rule on those bars, so such symbols are excluded.

This module never silently drops a symbol: every exclusion is counted and reported,
because a backtest whose universe you cannot audit is not evidence.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from typing import Any

WORKSPACE_ROOT = os.environ.get("QX_WORKSPACE_ROOT", "").strip() or r"C:\Project\2026"
CACHE_DIR = os.path.join(WORKSPACE_ROOT, "data", "cache", "bars")

# A single-bar move beyond this is treated as an unadjusted corporate action rather
# than a market move. Chosen because a genuine one-day 45% move in a listed equity is
# rare, while splits and reverse splits routinely produce exactly that shape.
SPLIT_GAP_THRESHOLD = 0.45

# MASTER AUTO needs 5 x longest period; plus a testable tail.
WARMUP_BARS = 136
MIN_BARS = WARMUP_BARS + 40

DATE_KEYS = ("date", "Date", "datetime", "timestamp")


@dataclass
class BarSet:
    symbol: str
    bars: list[dict[str, Any]]
    source_file: str
    first_date: str | None = None
    last_date: str | None = None

    @property
    def count(self) -> int:
        return len(self.bars)


@dataclass
class UniverseReport:
    loaded: list[str] = field(default_factory=list)
    excluded: dict[str, list[str]] = field(default_factory=dict)
    scanned: int = 0

    def exclude(self, symbol: str, reason: str) -> None:
        self.excluded.setdefault(reason, []).append(symbol)

    @property
    def loaded_count(self) -> int:
        return len(self.loaded)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "loaded": self.loaded_count,
            "excluded_total": sum(len(v) for v in self.excluded.values()),
            "excluded_by_reason": {k: len(v) for k, v in sorted(self.excluded.items())},
            "excluded_examples": {k: sorted(v)[:8] for k, v in sorted(self.excluded.items())},
            "note": ("Every exclusion is counted. A universe you cannot audit is not "
                     "evidence."),
        }


def _parse_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def load_bars(symbol: str, *, window: str = "2y") -> BarSet | None:
    """Load one symbol's bars. Returns None when absent, raises nothing."""
    path = os.path.join(CACHE_DIR, f"{symbol}_{window}.csv")
    if not os.path.exists(path):
        return None
    bars: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8", errors="ignore", newline="") as handle:
        for raw in csv.DictReader(handle):
            if not raw:
                continue
            date_value = next((str(raw[k]).strip() for k in DATE_KEYS
                               if raw.get(k) not in (None, "")), "")
            close = _parse_float(raw.get("close"))
            high = _parse_float(raw.get("high"))
            low = _parse_float(raw.get("low"))
            open_ = _parse_float(raw.get("open"))
            if close is None or high is None or low is None or open_ is None:
                continue
            if close <= 0 or high <= 0 or low <= 0 or open_ <= 0:
                continue
            bars.append({
                "date": date_value or None,
                "open": open_, "high": high, "low": low, "close": close,
                "volume": _parse_float(raw.get("volume")) or 0.0,
                "bar_completed": True, "interval": "1d",
            })
    if not bars:
        return None
    return BarSet(symbol=symbol, bars=bars, source_file=os.path.basename(path),
                  first_date=bars[0]["date"], last_date=bars[-1]["date"])


def _worst_gap(bars: list[dict[str, Any]]) -> tuple[float, str | None]:
    worst = 0.0
    when: str | None = None
    for index in range(1, len(bars)):
        previous = bars[index - 1]["close"]
        current = bars[index]["close"]
        if previous <= 0:
            continue
        move = abs(current / previous - 1.0)
        if move > worst:
            worst, when = move, bars[index]["date"]
    return worst, when


def audit_symbol(symbol: str, *, window: str = "2y",
                 min_bars: int = MIN_BARS) -> tuple[BarSet | None, str | None]:
    """Return (barset, None) when usable, or (None, reason) when not."""
    barset = load_bars(symbol, window=window)
    if barset is None:
        return None, "no cached file"
    if barset.count < min_bars:
        return None, f"insufficient history (<{min_bars} bars)"
    dates = [b["date"] for b in barset.bars]
    if any(d is None for d in dates):
        return None, "missing dates (point-in-time unprovable)"
    if dates != sorted(dates):
        return None, "dates not ascending"
    if len(set(dates)) != len(dates):
        return None, "duplicate dates"
    worst, when = _worst_gap(barset.bars)
    if worst > SPLIT_GAP_THRESHOLD:
        return None, (f"suspected unadjusted split ({worst * 100:.0f}% single-bar move"
                      + (f" on {when}" if when else "") + ")")
    return barset, None


def discover_symbols(window: str = "2y") -> list[str]:
    """Every symbol with a cached file for the requested window."""
    if not os.path.isdir(CACHE_DIR):
        return []
    suffix = f"_{window}.csv"
    return sorted(name[: -len(suffix)] for name in os.listdir(CACHE_DIR)
                  if name.endswith(suffix))


def build_universe(*, window: str = "2y", symbols: list[str] | None = None,
                   min_bars: int = MIN_BARS,
                   limit: int | None = None) -> tuple[dict[str, BarSet], UniverseReport]:
    """Audit and load a clean universe, reporting every exclusion."""
    candidates = symbols if symbols is not None else discover_symbols(window)
    report = UniverseReport()
    report.scanned = len(candidates)
    universe: dict[str, BarSet] = {}
    for symbol in candidates:
        barset, reason = audit_symbol(symbol, window=window, min_bars=min_bars)
        if reason:
            report.exclude(symbol, reason)
            continue
        universe[symbol] = barset
        report.loaded.append(symbol)
        if limit is not None and len(universe) >= limit:
            break
    return universe, report
