from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from qx.options.quality import FundamentalSnapshot


class FundamentalProvider(Protocol):
    def get_fundamentals(self, symbol: str) -> FundamentalSnapshot:
        """Return the latest available fundamental snapshot for a symbol."""


class EmptyFundamentalProvider:
    def get_fundamentals(self, symbol: str) -> FundamentalSnapshot:
        return FundamentalSnapshot()


class CachedFundamentalProvider:
    def __init__(
        self,
        provider: FundamentalProvider,
        cache_dir: Path = Path("data/cache/fundamentals"),
        refresh: bool = False,
    ) -> None:
        self.provider = provider
        self.cache_dir = cache_dir
        self.refresh = refresh

    def get_fundamentals(self, symbol: str) -> FundamentalSnapshot:
        normalized = symbol.strip().upper()
        cache_path = self.cache_dir / f"{normalized}.json"
        if cache_path.exists() and not self.refresh:
            return _snapshot_from_dict(json.loads(cache_path.read_text(encoding="utf-8")))

        snapshot = self.provider.get_fundamentals(normalized)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(snapshot.__dict__, indent=2), encoding="utf-8")
        return snapshot


class YFinanceFundamentalProvider:
    """Reads high-level fundamentals from yfinance.

    yfinance field coverage varies by symbol, so all fields are optional and the
    quality engine handles partial coverage explicitly.
    """

    def get_fundamentals(self, symbol: str) -> FundamentalSnapshot:
        import yfinance as yf  # type: ignore[import-untyped]

        ticker = yf.Ticker(symbol)
        info = dict(ticker.get_info() or {})
        return _snapshot_from_dict(
            {
                "market_cap": info.get("marketCap"),
                "eps_growth": info.get("earningsGrowth"),
                "revenue_growth": info.get("revenueGrowth"),
                "roe": info.get("returnOnEquity"),
                "debt_to_equity": _normalize_debt_to_equity(info.get("debtToEquity")),
                "profit_margin": info.get("profitMargins"),
                "free_cash_flow_positive": _positive_cash_flow(info.get("freeCashflow")),
            }
        )


def _snapshot_from_dict(payload: dict[str, object]) -> FundamentalSnapshot:
    return FundamentalSnapshot(
        market_cap=_optional_float(payload.get("market_cap")),
        eps_growth=_optional_float(payload.get("eps_growth")),
        revenue_growth=_optional_float(payload.get("revenue_growth")),
        roe=_optional_float(payload.get("roe")),
        debt_to_equity=_optional_float(payload.get("debt_to_equity")),
        profit_margin=_optional_float(payload.get("profit_margin")),
        free_cash_flow_positive=_optional_bool(payload.get("free_cash_flow_positive")),
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, str | int | float):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value > 0
    return None


def _normalize_debt_to_equity(value: object) -> float | None:
    raw_value = _optional_float(value)
    if raw_value is None:
        return None
    return raw_value / 100 if raw_value > 10 else raw_value


def _positive_cash_flow(value: object) -> bool | None:
    raw_value = _optional_float(value)
    if raw_value is None:
        return None
    return raw_value > 0
