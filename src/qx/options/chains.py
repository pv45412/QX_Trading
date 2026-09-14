from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class OptionContract:
    symbol: str
    expiration: date
    contract_symbol: str
    strike: float
    option_type: str
    bid: float
    ask: float
    last_price: float
    volume: int
    open_interest: int
    implied_volatility: float
    dte: int
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2 if self.bid > 0 and self.ask > 0 else self.last_price

    @property
    def spread_pct(self) -> float:
        mid = self.mid
        if mid <= 0:
            return 1.0
        return (self.ask - self.bid) / mid if self.ask >= self.bid else 1.0


class OptionsChainProvider(Protocol):
    def get_calls(self, symbol: str) -> list[OptionContract]:
        """Return available call contracts for a symbol."""

    def get_puts(self, symbol: str) -> list[OptionContract]:
        """Return available put contracts for a symbol."""


class YFinanceOptionsChainProvider:
    """Reads option chains from yfinance when available."""

    def get_calls(self, symbol: str) -> list[OptionContract]:
        import yfinance as yf  # type: ignore[import-untyped]

        ticker = yf.Ticker(symbol)
        expirations = list(getattr(ticker, "options", []) or [])
        contracts: list[OptionContract] = []
        for expiration_text in expirations[:8]:
            chain = ticker.option_chain(expiration_text)
            expiration = datetime.strptime(expiration_text, "%Y-%m-%d").date()
            contracts.extend(_calls_from_frame(symbol, expiration, chain.calls))
        return contracts

    def get_puts(self, symbol: str) -> list[OptionContract]:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        expirations = list(getattr(ticker, "options", []) or [])
        contracts: list[OptionContract] = []
        for expiration_text in expirations[:8]:
            chain = ticker.option_chain(expiration_text)
            expiration = datetime.strptime(expiration_text, "%Y-%m-%d").date()
            contracts.extend(_puts_from_frame(symbol, expiration, chain.puts))
        return contracts


def _calls_from_frame(
    symbol: str,
    expiration: date,
    frame: pd.DataFrame,
) -> list[OptionContract]:
    return _contracts_from_frame(symbol, expiration, frame, option_type="call")


def _puts_from_frame(
    symbol: str,
    expiration: date,
    frame: pd.DataFrame,
) -> list[OptionContract]:
    return _contracts_from_frame(symbol, expiration, frame, option_type="put")


def _contracts_from_frame(
    symbol: str,
    expiration: date,
    frame: pd.DataFrame,
    *,
    option_type: str,
) -> list[OptionContract]:
    today = date.today()
    dte = max((expiration - today).days, 0)
    contracts: list[OptionContract] = []
    for row in frame.to_dict("records"):
        contracts.append(
            OptionContract(
                symbol=symbol.upper(),
                expiration=expiration,
                contract_symbol=str(row.get("contractSymbol", "")),
                strike=float(row.get("strike", 0.0) or 0.0),
                option_type=option_type,
                bid=float(row.get("bid", 0.0) or 0.0),
                ask=float(row.get("ask", 0.0) or 0.0),
                last_price=float(row.get("lastPrice", 0.0) or 0.0),
                volume=int(row.get("volume", 0) or 0),
                open_interest=int(row.get("openInterest", 0) or 0),
                implied_volatility=float(row.get("impliedVolatility", 0.0) or 0.0),
                dte=dte,
            )
        )
    return contracts
