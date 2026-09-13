from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from qx.data.quotes import QuoteSnapshot
from qx.market.futures_evidence import (
    classify_continuity_readiness,
    inspect_futures_contracts,
    quote_evidence,
)


NOW = datetime(2026, 9, 11, 18, tzinfo=timezone.utc)
EXPIRY = datetime(2026, 9, 18, 4, tzinfo=timezone.utc)


def quote() -> QuoteSnapshot:
    return QuoteSnapshot(symbol="ES=F",provider="schwab",last=100,bid=99.75,ask=100.25,
        timestamp=NOW-timedelta(seconds=1),trade_timestamp=NOW-timedelta(seconds=2),
        resolved_symbol="/ESU26",asset_type="FUTURE",realtime=True,expiration=EXPIRY)


def test_fresh_explicit_quote_is_not_proof_of_continuity_or_a_trade_signal() -> None:
    result = quote_evidence(quote(), NOW)
    assert result["quote_status"] == "fresh_at_check"
    assert result["contract_status"] == "provider_identified"
    assert not result["continuous_cache_comparable"]
    assert not result["cash_close_synchronized"]
    assert result["continuity_status"] == "blocked"
    assert result["readiness_status"] == "blocked"
    assert result["readiness_blockers"] == [
        "explicit_contract_history_unverified",
        "continuous_series_comparability_unverified",
        "cash_session_synchronization_unverified",
    ]
    assert not result["live_signal_eligible"]
    assert quote_evidence(quote(),NOW+timedelta(seconds=60))["quote_status"] == "unverified_or_stale"


def test_continuity_requires_more_than_contract_identity_and_matching_history() -> None:
    evidence = {
        "contract_status": "provider_identified",
        "quote_status": "fresh_at_check",
        "history_status": "provider_contract_matched",
        "continuous_cache_comparable": False,
        "cash_close_synchronized": False,
    }
    result = classify_continuity_readiness(evidence)
    assert result["continuity_status"] == "blocked"
    assert result["readiness_status"] == "blocked"
    assert result["readiness_blockers"] == [
        "continuous_series_comparability_unverified",
        "cash_session_synchronization_unverified",
    ]
    assert not result["live_signal_eligible"]


def test_readiness_requires_each_explicit_evidence_check() -> None:
    evidence = {
        "contract_status": "provider_identified",
        "quote_status": "fresh_at_check",
        "history_status": "provider_contract_matched",
        "continuous_cache_comparable": True,
        "cash_close_synchronized": True,
    }
    result = classify_continuity_readiness(evidence)
    assert result["continuity_status"] == "verified"
    assert result["readiness_status"] == "evidence_ready"
    assert result["readiness_blockers"] == []
    assert not result["live_signal_eligible"]


@pytest.mark.parametrize("changes", [
    {"timestamp":None},{"trade_timestamp":None},{"realtime":False},{"realtime":None},
    {"timestamp":NOW+timedelta(seconds=1)},{"trade_timestamp":NOW-timedelta(seconds=61)},
    {"asset_type":"EQUITY"},{"resolved_symbol":"/NQU26"},{"resolved_symbol":"/ES"},
    {"resolved_symbol":"/ESZ26"},{"resolved_symbol":"/ESU27"},{"provider":"yfinance"},
    {"expiration":None},{"expiration":NOW-timedelta(days=1)},
    {"expiration":EXPIRY.replace(tzinfo=None)},{"bid":101},{"last":float("nan")},
    {"ask":float("inf")},{"last":True},
])
def test_missing_stale_mismatched_or_invalid_quotes_fail_closed(changes: dict[str, Any]) -> None:
    result = quote_evidence(replace(quote(),**changes),NOW)
    assert result["quote_status"] == "unverified_or_stale"
    assert not result["live_signal_eligible"]


class FakeClient:
    def __init__(self, defect: str | None = None) -> None:
        self.defect = defect
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.quote_calls: dict[str, int] = {}

    def get(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path,params))
        if path.endswith("quotes"):
            root = params["symbols"]
            self.quote_calls[root] = self.quote_calls.get(root,0)+1
            contract = root+"U26"
            expiry = EXPIRY
            if self.defect == "roll" and self.quote_calls[root] > 1:
                contract = root+"Z26"
                expiry = datetime(2026,12,18,5,tzinfo=timezone.utc)
            return {contract:{"symbol":contract,"assetMainType":"FUTURE","realtime":True,
                "quote":{"lastPrice":100,"bidPrice":99.75,"askPrice":100.25,
                    "quoteTime":int((NOW-timedelta(seconds=1)).timestamp()*1000),
                    "tradeTime":int((NOW-timedelta(seconds=2)).timestamp()*1000)},
                "reference":{"futureExpirationDate":int(expiry.timestamp()*1000)}}}
        if self.defect == "provider":
            raise RuntimeError("sensitive-request-secret")
        dates = pd.bdate_range("2026-08-03",periods=25,tz="UTC")
        candles = [{"datetime":int(day.timestamp()*1000),"open":100,"high":101,"low":99,"close":100,"volume":1000} for day in dates]
        if self.defect == "future":
            candles[-1]["datetime"] = int((NOW+timedelta(days=1)).timestamp()*1000)
        if self.defect == "geometry":
            candles[-1]["high"] = 90
        return {"symbol":"/OTHER" if self.defect == "identity" else params["symbol"],"candles":candles}


def test_exact_contract_history_is_checked_and_root_is_rechecked() -> None:
    client = FakeClient()
    report = inspect_futures_contracts(cast(Any, client), now=NOW)
    assert len(client.calls) == 8
    assert [params["symbol"] for path,params in client.calls if path.endswith("pricehistory")] == ["/ESU26","/ESU26","/NQU26","/NQU26"]
    assert all(row["history_status"] == "provider_contract_matched" for row in report["rows"])
    assert all(row["quote_status"] == "fresh_at_check" for row in report["rows"])
    assert all(not row["live_signal_eligible"] for row in report["rows"])
    assert report["model_calls"] == 0


def test_intraday_history_is_recorded_but_not_treated_as_fresh_outside_its_window() -> None:
    report = inspect_futures_contracts(cast(Any, FakeClient()), now=NOW)
    for row in report["rows"]:
        assert row["intraday_bars"] == 25
        assert row["intraday_status"] == "stale_at_check"
        assert row["intraday_last_timestamp"] is not None
        assert row["intraday_bar_age_seconds"] > 900


@pytest.mark.parametrize("defect",["provider","identity","future","geometry","roll"])
def test_bad_or_changed_history_never_certifies_continuity(defect: str) -> None:
    result = inspect_futures_contracts(cast(Any, FakeClient(defect)), now=NOW)
    expected = "contract_changed_during_check" if defect == "roll" else "history_or_provider_unavailable"
    assert all(row["history_status"] == expected for row in result["rows"])
    assert all(not row["live_signal_eligible"] for row in result["rows"])
    assert "sensitive" not in str(result)


def test_ui_entry_is_passive_and_explicit_check_shows_limitations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    monkeypatch.setattr("qx.data.factory._schwab_client",lambda settings:client)
    monkeypatch.setattr("qx.market.futures_evidence.inspect_futures_contracts",lambda selected:inspect_futures_contracts(selected,now=NOW))
    app = AppTest.from_string('import streamlit as st\nfrom qx.ui.pages.spx_dashboard import _render_contract_check\n_render_contract_check(st)').run()
    assert not app.exception and client.calls == []
    app.button[0].click().run()
    assert not app.exception and len(client.calls) == 8
    assert app.dataframe[0].value["Contract"].tolist() == ["/ESU26","/NQU26"]
    assert app.dataframe[0].value["Evidence"].tolist() == ["Blocked", "Blocked"]
    assert "continuous_series_comparability_unverified" in app.dataframe[0].value["Missing evidence"].iloc[0]
    assert any("not execution eligibility" in item.value for item in app.warning)
    app.run()
    assert len(client.calls) == 8
