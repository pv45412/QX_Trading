from datetime import date, datetime, timezone
from pathlib import Path

import json
import pytest

from qx.options.calendar_snapshot import (
    build_calendar_chain_snapshot,
    load_calendar_chain_snapshot,
    save_calendar_chain_snapshot,
)
from qx.options.chains import OptionContract


class StaticChainProvider:
    provider_name = "schwab"

    def get_calls(self, symbol: str) -> list[OptionContract]:
        return [_contract(symbol, "call", 100.0, 1.0, 1.2, 20)]

    def get_puts(self, symbol: str) -> list[OptionContract]:
        return [_contract(symbol, "put", 95.0, 0.0, 0.0, 0)]


def _contract(symbol: str, option_type: str, strike: float, bid: float, ask: float, open_interest: int) -> OptionContract:
    return OptionContract(symbol, date(2026, 10, 16), f"{symbol}{option_type}{strike}", strike, option_type, bid, ask, bid, 3, open_interest, 0.2, 34)


def test_calendar_snapshot_keeps_source_timestamp_and_quote_coverage(tmp_path: Path):
    snapshot = build_calendar_chain_snapshot(StaticChainProvider(), now=datetime(2026, 9, 12, tzinfo=timezone.utc))
    assert snapshot.source == "schwab"
    assert snapshot.expiration_count == 1
    assert snapshot.quoted_contract_count == 1
    assert snapshot.open_interest_contract_count == 1
    target = tmp_path / "calendar.json"
    save_calendar_chain_snapshot(snapshot, target)
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["source"] == "schwab"
    assert raw["contracts"][0]["expiration"] == "2026-10-16"
    restored = load_calendar_chain_snapshot(target)
    assert restored == snapshot


def test_calendar_snapshot_rejects_empty_or_mismatched_chains():
    class Empty:
        provider_name = "schwab"

        def get_calls(self, symbol: str) -> list[OptionContract]:
            return []

        def get_puts(self, symbol: str) -> list[OptionContract]:
            return []

    with pytest.raises(ValueError, match="No option contracts"):
        build_calendar_chain_snapshot(Empty())

    class Mismatched(StaticChainProvider):
        def get_calls(self, symbol: str) -> list[OptionContract]:
            return [_contract("SPY", "call", 100.0, 1.0, 1.2, 20)]

    with pytest.raises(ValueError, match="identity"):
        build_calendar_chain_snapshot(Mismatched())
