from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pytest

from qx.data.quotes import QuoteSnapshot
from qx.market.mover_briefing import mover_briefing
from qx.market.spx_dashboard import _opening_gap_read
from tests.unit.test_market_movers_validation import bars, candidate


def test_briefing_is_reproducible_and_changes_with_evidence():
    mover = candidate(bars())
    first = mover_briefing(mover)
    assert first == mover_briefing(mover)
    assert first["snapshot_id"] != mover_briefing(replace(mover, price=101))["snapshot_id"]
    assert "current_quote" in first["unknown"]
    assert first["mode"] == "deterministic_evidence_only"
    assert any("incomplete" in item for item in first["warnings"])


def test_nonfinite_evidence_fails_closed():
    with pytest.raises(ValueError):
        mover_briefing(replace(candidate(bars()), price=float("nan")))


def test_provider_name_does_not_imply_forecast_confidence():
    provider = SimpleNamespace(get_quote=lambda symbol: QuoteSnapshot(symbol=symbol, provider="schwab", last=110))
    result = _opening_gap_read(prior_spx_close=100, es_bars=pd.DataFrame({"close":[100,105]}), quote_provider=provider)
    assert result.confidence == "Unverified"
    assert result.updated_at == "quote timestamp unavailable"
    assert result.es_reference == 105
    assert result.es_change_points == 5
    assert result.implied_spx_open is None


def test_cached_daily_comparison_is_not_an_opening_forecast():
    result = _opening_gap_read(prior_spx_close=100, es_bars=pd.DataFrame({"close": [100, 105]}), quote_provider=None)
    assert result.es_reference == 100
    assert result.es_change_pct == 0.05
    assert result.implied_gap_pct is None
    assert "not an overnight move" in result.read


def test_single_cached_close_cannot_imply_zero_change():
    result = _opening_gap_read(prior_spx_close=100, es_bars=pd.DataFrame({"close": [105]}), quote_provider=None)
    assert result.es_reference is None
    assert result.es_change_pct is None


@pytest.mark.parametrize("last", [None, float("nan"), float("inf"), -1, 0])
def test_invalid_quote_falls_back_to_daily_comparison(last):
    provider = SimpleNamespace(get_quote=lambda symbol: QuoteSnapshot(symbol=symbol, provider="schwab", last=last))
    result = _opening_gap_read(prior_spx_close=100, es_bars=pd.DataFrame({"close": [100, 105]}), quote_provider=provider)
    assert result.data_source == "ES daily bars"
    assert result.es_reference == 100
    assert result.es_last == 105
    assert result.implied_spx_open is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, 0])
def test_invalid_reference_cannot_produce_opening_estimate(bad):
    result = _opening_gap_read(prior_spx_close=bad, es_bars=pd.DataFrame({"close":[100,105]}), quote_provider=None)
    assert result.implied_spx_open is None
    assert result.gap_type == "Unavailable"
