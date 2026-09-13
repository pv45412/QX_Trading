from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from dataclasses import replace

import pandas as pd

from qx.data.providers import MarketDataProvider
from qx.models.market import BarDataRequest
from qx.market.relative_strength import relative_strength


SECTOR_ETFS: dict[str, str] = {
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Information Technology": "XLK",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}

SECTOR_GROUPS: dict[str, str] = {
    "Communication Services": "Growth",
    "Consumer Discretionary": "Cyclical",
    "Consumer Staples": "Defensive",
    "Energy": "Value/Cyclical",
    "Financials": "Cyclical",
    "Health Care": "Defensive",
    "Industrials": "Cyclical",
    "Information Technology": "Growth",
    "Materials": "Cyclical",
    "Real Estate": "Rate Sensitive",
    "Utilities": "Defensive",
}


@dataclass(frozen=True)
class SectorRotationRow:
    sector: str
    etf: str
    group: str
    return_5d: float
    return_20d: float
    return_60d: float
    relative_5d: float
    relative_20d: float
    relative_60d: float
    acceleration: float
    distance_from_sma20: float
    distance_from_sma50: float
    rsi_14: float
    extension_risk_score: float
    above_sma50: bool
    rotation_status: str
    leadership_score: float
    rs20_aligned: float | None = None
    rs_momentum_5d: float | None = None
    rs_quadrant: str = "UNKNOWN"
    rs_status: str = "INSUFFICIENT_HISTORY"


@dataclass(frozen=True)
class SectorRotationResult:
    benchmark: str
    rows: list[SectorRotationRow]
    failures: dict[str, str]

    @property
    def leaders(self) -> list[SectorRotationRow]:
        return self.rows[:3]


def analyze_sector_rotation(
    provider: MarketDataProvider,
    *,
    period: str = "2y",
    benchmark: str = "SPY",
    max_workers: int = 8,
) -> SectorRotationResult:
    benchmark_bars = provider.get_daily_bars(BarDataRequest(symbol=benchmark, period=period))
    benchmark_5d = _return_over_bars(benchmark_bars, 5)
    benchmark_20d = _return_over_bars(benchmark_bars, 20)
    benchmark_60d = _return_over_bars(benchmark_bars, 60)
    rows: list[SectorRotationRow] = []
    failures: dict[str, str] = {}

    def load_sector(sector: str, etf: str) -> SectorRotationRow:
        bars = provider.get_daily_bars(BarDataRequest(symbol=etf, period=period))
        row = _sector_row(sector, etf, bars, benchmark_5d, benchmark_20d, benchmark_60d)
        rs = relative_strength(bars, benchmark_bars)
        return replace(row, rs20_aligned=rs.rs20, rs_momentum_5d=rs.momentum_5d,
                       rs_quadrant=rs.quadrant, rs_status=rs.status)

    workers = max(1, min(max_workers, len(SECTOR_ETFS)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_by_etf = {
            executor.submit(load_sector, sector, etf): etf
            for sector, etf in SECTOR_ETFS.items()
        }
        for future in as_completed(future_by_etf):
            etf = future_by_etf[future]
            try:
                rows.append(future.result())
            except Exception as exc:
                failures[etf] = str(exc)

    rows.sort(key=lambda row: (row.leadership_score, row.relative_20d), reverse=True)
    return SectorRotationResult(benchmark=benchmark, rows=rows, failures=failures)


def sector_rotation_frame(result: SectorRotationResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sector": row.sector,
                "etf": row.etf,
                "group": row.group,
                "5d": row.return_5d,
                "20d": row.return_20d,
                "60d": row.return_60d,
                "relative_5d": row.relative_5d,
                "relative_20d": row.relative_20d,
                "relative_60d": row.relative_60d,
                "acceleration": row.acceleration,
                "distance_from_sma20": row.distance_from_sma20,
                "distance_from_sma50": row.distance_from_sma50,
                "rsi_14": row.rsi_14,
                "extension_risk_score": row.extension_risk_score,
                "above_sma50": row.above_sma50,
                "rotation_status": row.rotation_status,
                "leadership_score": row.leadership_score,
                "rs20_aligned": row.rs20_aligned,
                "rs_momentum_5d": row.rs_momentum_5d,
                "rs_quadrant": row.rs_quadrant,
                "rs_status": row.rs_status,
            }
            for row in result.rows
        ]
    )


def _sector_row(
    sector: str,
    etf: str,
    bars: pd.DataFrame,
    benchmark_5d: float,
    benchmark_20d: float,
    benchmark_60d: float,
) -> SectorRotationRow:
    return_5d = _return_over_bars(bars, 5)
    return_20d = _return_over_bars(bars, 20)
    return_60d = _return_over_bars(bars, 60)
    sma20 = float(bars["close"].rolling(20).mean().dropna().iloc[-1])
    sma50 = float(bars["close"].rolling(50).mean().dropna().iloc[-1])
    close = float(bars["close"].iloc[-1])
    above_sma50 = close > sma50
    distance_from_sma20 = _distance_from_average(close, sma20)
    distance_from_sma50 = _distance_from_average(close, sma50)
    rsi_14 = _rsi(bars["close"], 14)
    relative_5d = return_5d - benchmark_5d
    relative_20d = return_20d - benchmark_20d
    relative_60d = return_60d - benchmark_60d
    acceleration = relative_5d - relative_20d
    rotation_status = _rotation_status(relative_5d, relative_20d, relative_60d, acceleration, above_sma50)
    leadership_score = _score_sector(
        return_5d,
        return_20d,
        return_60d,
        relative_5d,
        relative_20d,
        relative_60d,
        acceleration,
        above_sma50,
    )
    extension_risk_score = _extension_risk_score(
        distance_from_sma20,
        distance_from_sma50,
        rsi_14,
        acceleration,
        leadership_score,
    )
    return SectorRotationRow(
        sector=sector,
        etf=etf,
        group=SECTOR_GROUPS.get(sector, "Other"),
        return_5d=round(return_5d, 4),
        return_20d=round(return_20d, 4),
        return_60d=round(return_60d, 4),
        relative_5d=round(relative_5d, 4),
        relative_20d=round(relative_20d, 4),
        relative_60d=round(relative_60d, 4),
        acceleration=round(acceleration, 4),
        distance_from_sma20=round(distance_from_sma20, 4),
        distance_from_sma50=round(distance_from_sma50, 4),
        rsi_14=round(rsi_14, 2),
        extension_risk_score=round(extension_risk_score, 3),
        above_sma50=above_sma50,
        rotation_status=rotation_status,
        leadership_score=round(leadership_score, 3),
    )


def _score_sector(
    return_5d: float,
    return_20d: float,
    return_60d: float,
    relative_5d: float,
    relative_20d: float,
    relative_60d: float,
    acceleration: float,
    above_sma50: bool,
) -> float:
    score = 0.0
    score += 0.15 if return_5d > 0 else 0.0
    score += 0.20 if return_20d > 0 else 0.0
    score += 0.15 if return_60d > 0 else 0.0
    score += 0.15 if relative_5d > 0 else 0.0
    score += 0.20 if relative_20d > 0 else 0.0
    score += 0.10 if relative_60d > 0 else 0.0
    score += 0.05 if acceleration > 0 else 0.0
    score += 0.10 if above_sma50 else 0.0
    score += 0.05 if relative_20d > 0 and return_20d > 0 and above_sma50 else 0.0
    return min(score, 1.0)


def _rotation_status(
    relative_5d: float,
    relative_20d: float,
    relative_60d: float,
    acceleration: float,
    above_sma50: bool,
) -> str:
    if relative_20d > 0 and relative_60d > 0 and above_sma50:
        return "Leading"
    if relative_20d > 0 and acceleration > 0:
        return "Improving"
    if relative_20d <= 0 and acceleration > 0:
        return "Early Turn"
    if relative_20d > 0 and acceleration < 0:
        return "Losing Momentum"
    if relative_5d < 0 and relative_20d < 0:
        return "Lagging"
    return "Neutral"


def _return_over_bars(bars: pd.DataFrame, bars_back: int) -> float:
    if len(bars) <= bars_back:
        return 0.0
    current = float(bars["close"].iloc[-1])
    previous = float(bars["close"].iloc[-bars_back - 1])
    if previous <= 0:
        return 0.0
    return (current / previous) - 1.0


def _distance_from_average(close: float, average: float) -> float:
    if average <= 0:
        return 0.0
    return (close / average) - 1.0


def _rsi(close: pd.Series, period: int) -> float:
    if len(close) <= period:
        return 50.0
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    latest_loss = float(loss.dropna().iloc[-1]) if not loss.dropna().empty else 0.0
    latest_gain = float(gain.dropna().iloc[-1]) if not gain.dropna().empty else 0.0
    if latest_loss <= 0:
        return 100.0 if latest_gain > 0 else 50.0
    relative_strength = latest_gain / latest_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _extension_risk_score(
    distance_from_sma20: float,
    distance_from_sma50: float,
    rsi_14: float,
    acceleration: float,
    leadership_score: float,
) -> float:
    score = 0.0
    score += 0.30 if distance_from_sma20 > 0.08 else 0.0
    score += 0.25 if distance_from_sma50 > 0.15 else 0.0
    score += 0.25 if rsi_14 >= 70 else 0.0
    score += 0.10 if acceleration < 0 and leadership_score >= 0.70 else 0.0
    score += 0.10 if distance_from_sma20 > 0.12 else 0.0
    return min(score, 1.0)
