from __future__ import annotations

from datetime import date, datetime
from typing import Any

from qx.brokers.schwab.client import SchwabApiClient
from qx.brokers.schwab.symbols import schwab_option_chain_symbol
from qx.options.chains import OptionContract


class SchwabOptionsChainProvider:
    """Reads option chains from Schwab's market data API."""

    provider_name = "schwab"

    def __init__(
        self,
        client: SchwabApiClient,
        *,
        min_days_to_expiration: int = 30,
        max_days_to_expiration: int = 180,
        strike_count: int = 30,
    ) -> None:
        self.client = client
        self.min_days_to_expiration = min_days_to_expiration
        self.max_days_to_expiration = max_days_to_expiration
        self.strike_count = strike_count

    def get_calls(self, symbol: str) -> list[OptionContract]:
        return self._get_contracts(symbol, contract_type="CALL")

    def get_puts(self, symbol: str) -> list[OptionContract]:
        return self._get_contracts(symbol, contract_type="PUT")

    def _get_contracts(self, symbol: str, *, contract_type: str) -> list[OptionContract]:
        canonical_symbol = symbol.upper()
        payload = self.client.get(
            "/marketdata/v1/chains",
            params={
                "symbol": schwab_option_chain_symbol(canonical_symbol),
                "contractType": contract_type,
                "strikeCount": self.strike_count,
                "includeUnderlyingQuote": "false",
                "strategy": "SINGLE",
                "range": "ALL",
                "fromDate": date.today().isoformat(),
                "toDate": _days_from_today(self.max_days_to_expiration).isoformat(),
            },
        )
        map_key = "callExpDateMap" if contract_type == "CALL" else "putExpDateMap"
        return _parse_contract_map(
            canonical_symbol,
            payload.get(map_key, {}),
            min_dte=self.min_days_to_expiration,
            max_dte=self.max_days_to_expiration,
            option_type=contract_type.lower(),
        )


def _parse_contract_map(
    symbol: str,
    contract_map: object,
    *,
    min_dte: int,
    max_dte: int,
    option_type: str,
) -> list[OptionContract]:
    if not isinstance(contract_map, dict):
        return []

    contracts: list[OptionContract] = []
    for expiration_key, strikes in contract_map.items():
        expiration, dte = _parse_expiration_key(str(expiration_key))
        if dte < min_dte or dte > max_dte or not isinstance(strikes, dict):
            continue
        for strike_text, raw_contracts in strikes.items():
            strike = _safe_float(strike_text)
            if not isinstance(raw_contracts, list):
                continue
            for raw_contract in raw_contracts:
                if isinstance(raw_contract, dict):
                    contracts.append(
                        _contract_from_payload(
                            symbol,
                            expiration,
                            dte,
                            strike,
                            raw_contract,
                            option_type=option_type,
                        )
                    )
    return contracts


def _contract_from_payload(
    symbol: str,
    expiration: date,
    dte: int,
    strike: float,
    payload: dict[str, Any],
    *,
    option_type: str,
) -> OptionContract:
    return OptionContract(
        symbol=symbol,
        expiration=expiration,
        contract_symbol=str(payload.get("symbol", payload.get("contractSymbol", ""))),
        strike=_safe_float(payload.get("strikePrice", strike)),
        option_type=option_type,
        bid=_safe_float(payload.get("bid", 0.0)),
        ask=_safe_float(payload.get("ask", 0.0)),
        last_price=_safe_float(payload.get("last", payload.get("lastPrice", 0.0))),
        volume=int(payload.get("totalVolume", payload.get("volume", 0)) or 0),
        open_interest=int(payload.get("openInterest", 0) or 0),
        implied_volatility=_safe_float(payload.get("volatility", payload.get("impliedVolatility", 0.0))),
        dte=dte,
        delta=_safe_float(payload.get("delta", 0.0)),
        gamma=_safe_float(payload.get("gamma", 0.0)),
        theta=_safe_float(payload.get("theta", 0.0)),
        vega=_safe_float(payload.get("vega", 0.0)),
    )


def _parse_expiration_key(expiration_key: str) -> tuple[date, int]:
    # Schwab keys commonly look like "2026-01-16:45".
    date_text, _, dte_text = expiration_key.partition(":")
    expiration = datetime.strptime(date_text, "%Y-%m-%d").date()
    if dte_text:
        return expiration, int(dte_text)
    return expiration, max((expiration - date.today()).days, 0)


def _days_from_today(days: int) -> date:
    return date.fromordinal(date.today().toordinal() + days)


def _safe_float(value: object) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, str | int | float):
            return float(value)
        return 0.0
    except (TypeError, ValueError):
        return 0.0
