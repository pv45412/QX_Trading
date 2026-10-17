"""Canonical read-only live providers for Phase 9 and Phase 10 context."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
from typing import Any, Protocol

from qx.brokers.schwab.client import SchwabApiClient
from qx.brokers.schwab.symbols import schwab_option_chain_symbol
from qx.options_expression.models import (
    OptionContract,
    OptionGreekProvenance,
    OptionGreeks,
    OptionsContext,
)
from qx.portfolio.models import AccountRiskContext


class CanonicalOptionChainSnapshotProvider(Protocol):
    provider_name: str

    def get_option_chain_snapshot(self, symbol: str) -> OptionsContext | None:
        ...


class CanonicalAccountSnapshotProvider(Protocol):
    provider_name: str

    def get_account_risk_snapshot(self) -> AccountRiskContext | None:
        ...


class SchwabCanonicalOptionChainSnapshotProvider:
    provider_name = "schwab"

    def __init__(
        self,
        client: SchwabApiClient,
        *,
        max_days_to_expiration: int = 180,
        strike_count: int = 60,
        max_quote_age_seconds: float = 60.0,
    ) -> None:
        self.client = client
        self.max_days_to_expiration = max_days_to_expiration
        self.strike_count = strike_count
        self.max_quote_age_seconds = max_quote_age_seconds

    def get_option_chain_snapshot(self, symbol: str) -> OptionsContext | None:
        canonical_symbol = symbol.upper()
        payload = self.client.get(
            "/marketdata/v1/chains",
            params={
                "symbol": schwab_option_chain_symbol(canonical_symbol),
                "contractType": "ALL",
                "strikeCount": self.strike_count,
                "includeUnderlyingQuote": "true",
                "strategy": "SINGLE",
                "range": "ALL",
                "fromDate": date.today().isoformat(),
                "toDate": (date.today() + timedelta(days=self.max_days_to_expiration)).isoformat(),
            },
        )
        retrieved_at = datetime.now(timezone.utc)
        underlying_price = _number(payload.get("underlyingPrice"))
        if underlying_price is None or underlying_price <= 0:
            return None

        chain: dict[str, dict[float, dict[str, OptionContract]]] = {}
        timestamps: list[datetime] = []
        raw_contract_count = 0
        accepted_contract_count = 0
        for map_key, option_label, is_call in (
            ("callExpDateMap", "CALL", True),
            ("putExpDateMap", "PUT", False),
        ):
            contract_map = payload.get(map_key, {})
            if not isinstance(contract_map, dict):
                continue
            for expiration_key, strikes in contract_map.items():
                if not isinstance(strikes, dict):
                    continue
                expiration, dte = _expiration(str(expiration_key))
                for strike_key, raw_contracts in strikes.items():
                    strike = _number(strike_key)
                    if strike is None or not isinstance(raw_contracts, list):
                        continue
                    for raw in raw_contracts:
                        if not isinstance(raw, dict):
                            continue
                        raw_contract_count += 1
                        quote_as_of = _payload_timestamp(raw)
                        contract_symbol = str(
                            raw.get("symbol", raw.get("contractSymbol", ""))
                        ).strip()
                        if quote_as_of is None or not contract_symbol:
                            continue
                        timestamps.append(quote_as_of)
                        accepted_contract_count += 1
                        greeks = _greeks(raw, quote_as_of)
                        multiplier = _number(
                            raw.get("multiplier", raw.get("contractMultiplier"))
                        )
                        if multiplier is None or not math.isfinite(multiplier) or multiplier <= 0:
                            multiplier = None
                        contract = OptionContract(
                            symbol=contract_symbol,
                            underlying_symbol=canonical_symbol,
                            strike=strike,
                            expiration=expiration,
                            dte=dte,
                            is_call=is_call,
                            bid=_number(raw.get("bid")),
                            ask=_number(raw.get("ask")),
                            mark=_number(raw.get("mark", raw.get("last", raw.get("lastPrice")))),
                            volume=int(_number(raw.get("totalVolume", raw.get("volume"))) or 0),
                            open_interest=int(_number(raw.get("openInterest")) or 0),
                            implied_volatility=_normalized_iv(
                                _number(raw.get("volatility", raw.get("impliedVolatility")))
                            ),
                            greeks=greeks,
                            quote_as_of=quote_as_of.isoformat(),
                            quote_age_seconds=max(
                                0.0, (retrieved_at - quote_as_of).total_seconds()
                            ),
                            contract_multiplier=multiplier,
                            multiplier_provenance=(
                                "BROKER_PROVIDED" if multiplier is not None else "UNAVAILABLE"
                            ),
                        )
                        chain.setdefault(expiration, {}).setdefault(strike, {})[
                            option_label
                        ] = contract
        if not chain or not timestamps:
            return None
        data_as_of = max(timestamps)
        max_age_seconds = max(0.0, (retrieved_at - min(timestamps)).total_seconds())
        freshness = "FRESH" if max_age_seconds <= self.max_quote_age_seconds else "STALE"
        sync_status = (
            "SYNCED" if accepted_contract_count == raw_contract_count else "PARTIAL"
        )
        return OptionsContext(
            underlying_symbol=canonical_symbol,
            underlying_price=underlying_price,
            data_as_of=data_as_of.isoformat(),
            source=self.provider_name,
            freshness=freshness,
            publication_state="RESEARCH_ONLY",
            sync_status=sync_status,
            retrieved_at=retrieved_at.isoformat(),
            chain=chain,
            iv_raw=_normalized_iv(_number(payload.get("volatility"))),
            iv_provenance=(
                "BROKER_PROVIDED" if payload.get("volatility") is not None else "UNAVAILABLE"
            ),
            iv_data_as_of=data_as_of.isoformat(),
        )


def _expiration(value: str) -> tuple[str, int]:
    expiration, _, dte = value.partition(":")
    if dte.isdigit():
        return expiration, int(dte)
    try:
        return expiration, max((date.fromisoformat(expiration) - date.today()).days, 0)
    except ValueError:
        return expiration, 0


def _payload_timestamp(payload: dict[str, Any]) -> datetime | None:
    for key in ("quoteTimeInLong", "tradeTimeInLong"):
        value = _number(payload.get(key))
        if value is not None and value > 0:
            return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
    for key in ("quoteTime", "tradeTime"):
        value = payload.get(key)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.astimezone(timezone.utc)
            except ValueError:
                continue
    return None


def _greeks(payload: dict[str, Any], quote_as_of: datetime) -> OptionGreeks:
    values = {
        name: _number(payload.get(name))
        for name in ("delta", "gamma", "theta", "vega")
    }
    available = all(value is not None for value in values.values())
    if not available:
        values = {name: None for name in values}
    return OptionGreeks(
        **values,
        provenance=(
            OptionGreekProvenance.BROKER_PROVIDED
            if available
            else OptionGreekProvenance.UNAVAILABLE
        ),
        broker_source="schwab" if available else None,
        quote_timestamp=quote_as_of.isoformat() if available else None,
    )


def _normalized_iv(value: float | None) -> float | None:
    if value is None:
        return None
    return value / 100.0 if value > 3.0 else value


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        return number if number == number else None
    except (TypeError, ValueError):
        return None
