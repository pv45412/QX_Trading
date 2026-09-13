"""Versioned, source-attributed SPX option-chain snapshots for calendar research."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from qx.options.chains import OptionContract, OptionsChainProvider


@dataclass(frozen=True)
class CalendarChainSnapshot:
    schema_version: int
    symbol: str
    source: str
    retrieved_at: str
    contracts: tuple[OptionContract, ...]
    expiration_count: int
    quoted_contract_count: int
    open_interest_contract_count: int


def build_calendar_chain_snapshot(
    provider: OptionsChainProvider,
    *,
    symbol: str = "SPX",
    now: datetime | None = None,
) -> CalendarChainSnapshot:
    """Fetch one complete chain snapshot without inventing IV or event fields."""
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("Option-chain symbol is required")
    calls = provider.get_calls(normalized_symbol)
    puts = provider.get_puts(normalized_symbol)
    contracts = tuple((*calls, *puts))
    if not contracts:
        raise ValueError("No option contracts returned")
    if any(contract.symbol.upper() != normalized_symbol for contract in contracts):
        raise ValueError("Option-chain symbol identity mismatch")
    source = str(getattr(provider, "provider_name", "unknown")).strip().lower() or "unknown"
    quote_count = sum(contract.bid > 0 and contract.ask > 0 and contract.ask >= contract.bid for contract in contracts)
    open_interest_count = sum(contract.open_interest > 0 for contract in contracts)
    return CalendarChainSnapshot(
        schema_version=1,
        symbol=normalized_symbol,
        source=source,
        retrieved_at=(now or datetime.now(timezone.utc)).isoformat(),
        contracts=contracts,
        expiration_count=len({contract.expiration for contract in contracts}),
        quoted_contract_count=quote_count,
        open_interest_contract_count=open_interest_count,
    )


def save_calendar_chain_snapshot(snapshot: CalendarChainSnapshot, path: Path) -> None:
    """Persist the raw contract values plus source and retrieval time for replay."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(snapshot)
    payload["contracts"] = [
        {**asdict(contract), "expiration": contract.expiration.isoformat()}
        for contract in snapshot.contracts
    ]
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def load_calendar_chain_snapshot(path: Path) -> CalendarChainSnapshot:
    """Load a persisted snapshot for passive display without calling a provider."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError("Unsupported calendar-chain snapshot schema")
        contracts_raw = raw.get("contracts")
        if not isinstance(contracts_raw, list):
            raise ValueError("Calendar-chain contracts are missing")
        contracts = tuple(_contract_from_saved_payload(contract) for contract in contracts_raw)
        snapshot = CalendarChainSnapshot(
            schema_version=1,
            symbol=str(raw["symbol"]).strip().upper(),
            source=str(raw["source"]).strip().lower(),
            retrieved_at=str(raw["retrieved_at"]),
            contracts=contracts,
            expiration_count=int(raw["expiration_count"]),
            quoted_contract_count=int(raw["quoted_contract_count"]),
            open_interest_contract_count=int(raw["open_interest_contract_count"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid calendar-chain snapshot") from exc
    if not snapshot.symbol or not snapshot.source or not snapshot.contracts:
        raise ValueError("Invalid calendar-chain snapshot")
    if any(contract.symbol.upper() != snapshot.symbol for contract in snapshot.contracts):
        raise ValueError("Calendar-chain snapshot symbol identity mismatch")
    return snapshot


def _contract_from_saved_payload(payload: object) -> OptionContract:
    if not isinstance(payload, dict):
        raise ValueError("Invalid option contract")
    return OptionContract(
        symbol=str(payload["symbol"]).strip().upper(),
        expiration=datetime.strptime(str(payload["expiration"]), "%Y-%m-%d").date(),
        contract_symbol=str(payload["contract_symbol"]),
        strike=float(payload["strike"]),
        option_type=str(payload["option_type"]),
        bid=float(payload["bid"]),
        ask=float(payload["ask"]),
        last_price=float(payload["last_price"]),
        volume=int(payload["volume"]),
        open_interest=int(payload["open_interest"]),
        implied_volatility=float(payload["implied_volatility"]),
        dte=int(payload["dte"]),
    )
