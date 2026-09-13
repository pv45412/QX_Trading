from datetime import timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from qx.market.movers import (
    _candidate_from_bars,
    _candidate_for_symbol,
    _mover_action,
    _options_quality,
    _tape_status,
    market_movers_frame,
    scan_market_movers,
)


def bars():
    return pd.DataFrame(
        {
            "open": [100.0] * 22,
            "high": [110.0] * 22,
            "low": [90.0] * 22,
            "close": [100.0] * 22,
            "volume": [1000.0] * 21 + [10000.0],
        },
        index=pd.bdate_range("2026-08-10", periods=22),
    )


def metadata():
    return SimpleNamespace(
        get=lambda symbol: SimpleNamespace(name="Test", sector="Test", industry="Test")
    )


def candidate(frame):
    return _candidate_from_bars("TEST", frame, metadata(), None)


@pytest.mark.parametrize(
    "kind", ["negative_volume", "outside_candle", "nan", "zero_price", "duplicate", "unsorted"]
)
def test_invalid_bars_are_rejected(kind):
    frame = bars()
    if kind == "negative_volume":
        frame.iloc[-1, 4] = -1
    if kind == "outside_candle":
        frame.iloc[-1, 3] = 200
    if kind == "nan":
        frame.iloc[-1, 3] = float("nan")
    if kind == "zero_price":
        frame.iloc[-1, 3] = 0
    if kind == "duplicate":
        frame.index = pd.DatetimeIndex([frame.index[0]] * len(frame))
    if kind == "unsorted":
        frame = frame.iloc[::-1]
    with pytest.raises(ValueError):
        candidate(frame)


def test_rvol_excludes_latest_session():
    frame = bars()
    frame.attrs["provenance"] = {"actual_source": "fixture"}
    result = candidate(frame)
    assert result.relative_volume_20d == 10
    assert result.avg_volume_20d == 1000
    assert result.actual_source == "fixture"
    assert result.bar_date == frame.index[-1].date().isoformat()
    assert result.freshness == "Unchecked"


def test_zero_volume_baseline_is_rejected():
    frame = bars()
    frame["volume"] = 0
    with pytest.raises(ValueError):
        candidate(frame)


def test_risk_precedence_and_negative_day_gates():
    assert _mover_action(0.4, 2, 0.2, 1_000_000, 0.05, 1e8) == "Distribution Risk"
    assert _mover_action(0.88, 2, 1, 1_000_000, -0.1, 1e8) == "Monitor"
    assert _tape_status(0.88, 2, 1, -0.1) == "Neutral"
    assert _mover_action(0.78, 1.5, 0.65, 1_000_000, 0.01, 1e8) == "Review Now"
    assert _tape_status(0.78, 1.5, 0.65, 0.01) == "Accumulation Surge"


def test_options_labels_do_not_claim_contract_liquidity():
    assert _options_quality(2e6, 2e8, 0) == "Underlying Review"
    assert _options_quality(2e6, 2e8, 6e9) == "Underlying Liquid"
    assert _options_quality(100, 1000, 6e9) == "Low Underlying Liquidity"


def test_empty_result_frame_keeps_required_columns():
    frame = market_movers_frame([])
    assert frame.empty
    assert frame["tape_status"].isin(["Accumulation Surge"]).sum() == 0
    assert (frame["rectangle_score"] > 0).sum() == 0


def test_completed_session_and_staleness_guards():
    frame = bars()
    frame.index = pd.bdate_range(end="2026-08-28", periods=22)
    provider = SimpleNamespace(get_daily_bars=lambda request: frame)
    last = frame.index[-1]
    now = last.to_pydatetime().replace(hour=18, tzinfo=timezone.utc)
    result = _candidate_for_symbol("TEST", provider, "2y", metadata(), None, now)
    assert result.latest_volume == 1000
    assert result.freshness == "Session-aligned"
    with pytest.raises(ValueError, match="Missing, stale"):
        _candidate_for_symbol("TEST", provider, "2y", metadata(), None, now + pd.Timedelta(days=10))


def test_normalized_symbols_are_deduplicated():
    result = scan_market_movers(
        ["test", " TEST "],
        SimpleNamespace(get_daily_bars=lambda request: bars()),
        metadata_store=metadata(),
        enrich_metadata_limit=0,
    )
    assert result.total_symbols == 1
    assert len(result.candidates) == 1


@pytest.mark.parametrize("shares,dollars", [(499999, 1e8), (1e6, 9999999)])
def test_review_now_requires_both_liquidity_baselines(shares, dollars):
    assert _mover_action(0.95, 3, 0.9, shares, 0.08, dollars) == "Liquidity Review"
    assert _mover_action(0.95, 3, 0.2, shares, 0.08, dollars) == "Distribution Risk"


def test_liquidity_boundary_is_inclusive():
    assert _mover_action(0.95, 3, 0.9, 500000, 0.08, 1e7) == "Review Now"


def test_dollar_volume_uses_prior_session_traded_value():
    frame = bars()
    frame.iloc[-1, frame.columns.get_loc("close")] = 110
    assert candidate(frame).dollar_volume == 100000


def test_unchanged_candles_do_not_count_as_up_volume():
    assert candidate(bars()).accumulation_ratio == 1.0


def test_equal_scores_have_stable_symbol_order():
    result = scan_market_movers(
        ["ZZZ", "AAA"], SimpleNamespace(get_daily_bars=lambda request: bars()),
        metadata_store=metadata(), enrich_metadata_limit=0,
    )
    assert [item.symbol for item in result.candidates] == ["AAA", "ZZZ"]
