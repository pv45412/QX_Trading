from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient
from fastapi import FastAPI

from qx.interfaces import qx_v2, web
from qx.opportunities.publisher import OpportunityPublisher
from qx.opportunities.repository import OpportunityRepository
from qx.pipeline import market_data_quality
from qx.pipeline.market_data_quality import (
    MarketDataQualityStatus,
    audit_bar_frame,
    audit_cache_file,
    exact_cache_candidates,
    load_audited_bars,
    load_live_audited_bars,
)


EVALUATION = datetime(2026, 9, 15, 14, 42, tzinfo=timezone.utc)


def _write_bars(path: Path, timestamps: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "date": timestamps,
            "open": [100.0 + index for index in range(len(timestamps))],
            "high": [101.0 + index for index in range(len(timestamps))],
            "low": [99.0 + index for index in range(len(timestamps))],
            "close": [100.5 + index for index in range(len(timestamps))],
            "volume": [1000.0] * len(timestamps),
        }
    ).to_csv(path, index=False)


def _complete_five_minute_timestamps() -> list[str]:
    return [
        timestamp.isoformat()
        for timestamp in pd.date_range(
            "2026-09-15T09:30:00-04:00",
            "2026-09-15T10:35:00-04:00",
            freq="5min",
        )
    ]


def _bar_frame(timestamps: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0 + index for index in range(len(timestamps))],
            "high": [101.0 + index for index in range(len(timestamps))],
            "low": [99.0 + index for index in range(len(timestamps))],
            "close": [100.5 + index for index in range(len(timestamps))],
            "volume": [1000.0] * len(timestamps),
        },
        index=pd.DatetimeIndex(timestamps),
    )


def test_live_bars_preserve_utc_and_exclude_only_incomplete_candle():
    timestamps = _complete_five_minute_timestamps()
    timestamps.append("2026-09-15T10:40:00-04:00")

    class Provider:
        provider_name = "schwab"

        def get_intraday_bars(self, request):
            assert request.symbol == "SPY"
            assert request.period == "10d"
            assert request.interval_minutes == 5
            assert request.include_extended_hours is False
            frame = _bar_frame(timestamps)
            frame.index = frame.index.tz_convert("UTC")
            return frame

    result = load_live_audited_bars(Provider(), "SPY", "5m", EVALUATION)

    assert result.bars is not None
    assert result.quality_report.status == MarketDataQualityStatus.PARTIAL
    assert result.quality_report.timestamp_timezone == "UTC"
    assert result.quality_report.bar_count == len(timestamps)
    assert result.quality_report.usable_bar_count == len(timestamps) - 1
    assert result.quality_report.incomplete_candle_count == 1
    assert result.quality_report.data_as_of == datetime(
        2026, 9, 15, 14, 35, tzinfo=timezone.utc
    )
    assert len(result.quality_report.source_content_sha256 or "") == 64


def test_live_bar_audit_does_not_repair_duplicate_timestamps():
    timestamps = _complete_five_minute_timestamps()
    frame = _bar_frame([*timestamps, timestamps[-1]])

    bars, report = audit_bar_frame(
        frame,
        "SPY",
        "5m",
        EVALUATION,
        source="schwab",
        retrieved_at=EVALUATION,
    )

    assert not bars.empty
    assert report.publication_allowed is False
    assert report.status == MarketDataQualityStatus.BLOCKED
    assert report.duplicate_count == 1
    assert "DUPLICATE_BARS" in report.reason_codes


def test_live_hourly_bars_are_session_aligned_from_thirty_minute_source():
    timestamps = [
        timestamp.isoformat()
        for timestamp in pd.date_range(
            "2026-09-15T09:30:00-04:00",
            "2026-09-15T10:40:00-04:00",
            freq="30min",
        )
    ]

    class Provider:
        provider_name = "schwab"

        def get_intraday_bars(self, request):
            assert request.interval_minutes == 30
            frame = _bar_frame(timestamps)
            frame.index = frame.index.tz_convert("UTC")
            return frame

    result = load_live_audited_bars(Provider(), "SPY", "1h", EVALUATION)

    assert result.bars is not None
    assert result.quality_report.requested_timeframe == "1h"
    assert result.quality_report.observed_timeframe == "1h"
    assert result.quality_report.source_file == "schwab:30m->1h"
    assert result.quality_report.data_as_of == datetime(
        2026, 9, 15, 13, 30, tzinfo=timezone.utc
    )
    assert result.bars.iloc[0]["open"] == 100.0
    assert result.bars.iloc[0]["close"] == 101.5
    assert result.bars.iloc[0]["volume"] == 2000.0


def test_live_daily_bars_use_latest_completed_session():
    class Provider:
        provider_name = "schwab"

        def get_daily_bars(self, request):
            assert request.symbol == "SPY"
            assert request.period == "1y"
            return _bar_frame(["2026-09-14", "2026-09-15", "2026-09-16"])

    evaluation = datetime(2026, 9, 16, 16, 0, tzinfo=timezone.utc)
    result = load_live_audited_bars(Provider(), "SPY", "1d", evaluation)

    assert result.bars is not None
    assert result.quality_report.status == MarketDataQualityStatus.PARTIAL
    assert result.quality_report.data_as_of == datetime(
        2026, 9, 15, tzinfo=timezone.utc
    )
    assert result.quality_report.reason_codes == ["INCOMPLETE_DAILY_CANDLE_EXCLUDED"]


def test_live_daily_bars_complete_lagging_daily_history_from_full_intraday_session():
    evaluation = datetime(2026, 9, 17, 21, 0, tzinfo=timezone.utc)
    timestamps = pd.date_range(
        "2026-09-17T09:30:00-04:00",
        periods=13,
        freq="30min",
    )

    class Provider:
        provider_name = "schwab"

        def get_daily_bars(self, request):
            return _bar_frame(["2026-09-15", "2026-09-16"])

        def get_intraday_bars(self, request):
            assert request.interval_minutes == 30
            assert request.include_extended_hours is False
            return _bar_frame([timestamp.isoformat() for timestamp in timestamps])

    result = load_live_audited_bars(Provider(), "SPY", "1d", evaluation)

    assert result.bars is not None
    assert result.quality_report.status == MarketDataQualityStatus.PASS
    assert result.quality_report.source_file == "schwab:daily+30m->1d"
    assert result.quality_report.data_as_of == datetime(
        2026, 9, 17, tzinfo=timezone.utc
    )
    assert result.bars.iloc[-1]["open"] == 100.0
    assert result.bars.iloc[-1]["close"] == 112.5
    assert result.bars.iloc[-1]["volume"] == 13000.0


def test_live_daily_bars_reject_incomplete_intraday_daily_completion():
    evaluation = datetime(2026, 9, 17, 21, 0, tzinfo=timezone.utc)
    timestamps = pd.date_range(
        "2026-09-17T09:30:00-04:00",
        periods=12,
        freq="30min",
    )

    class Provider:
        provider_name = "schwab"

        def get_daily_bars(self, request):
            return _bar_frame(["2026-09-15", "2026-09-16"])

        def get_intraday_bars(self, request):
            return _bar_frame([timestamp.isoformat() for timestamp in timestamps])

    result = load_live_audited_bars(Provider(), "SPY", "1d", evaluation)

    assert result.bars is None
    assert result.quality_report.source_file == "schwab"
    assert "STALE_BARS" in result.quality_report.reason_codes


def test_live_api_uses_audited_provider_bars_without_cache(monkeypatch, tmp_path):
    timestamps = [
        timestamp.isoformat()
        for day in (
            "2026-09-10T09:30:00-04:00",
            "2026-09-11T09:30:00-04:00",
            "2026-09-14T09:30:00-04:00",
        )
        for timestamp in pd.date_range(day, periods=78, freq="5min")
    ]
    timestamps.extend(
        timestamp.isoformat()
        for timestamp in pd.date_range(
            "2026-09-15T09:30:00-04:00",
            "2026-09-15T10:40:00-04:00",
            freq="5min",
        )
    )

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return EVALUATION.astimezone(tz)

    class Provider:
        provider_name = "schwab"

        def get_intraday_bars(self, request):
            frame = _bar_frame(timestamps)
            frame.index = frame.index.tz_convert("UTC")
            return frame

    repository = OpportunityRepository(tmp_path / "opportunities.db")
    publisher = OpportunityPublisher(repository, environment_id="local")
    app = FastAPI()
    app.include_router(
        qx_v2.create_qx_v2_router(
            tmp_path,
            live_bar_provider=Provider(),
            opportunity_publisher=publisher,
        )
    )
    monkeypatch.setattr(qx_v2, "datetime", Clock)
    monkeypatch.setattr(market_data_quality, "datetime", Clock)

    response = TestClient(app).post("/api/v2/qx/evaluate/SPY?timeframe=5m")

    assert response.status_code == 200
    payload = response.json()
    dependency = payload["data_dependencies"]["bars"]
    assert payload["current_lifecycle_state"] != "BLOCKED"
    assert "NO_BARS_AT_OR_BEFORE_EVALUATION_TIMESTAMP" not in payload["reason_codes"]
    assert dependency["source"] == "schwab"
    assert dependency["quality_status"] == "PARTIAL"
    assert dependency["quality_reason_codes"] == ["INCOMPLETE_CURRENT_CANDLE_EXCLUDED"]
    assert dependency["data_as_of"] == "2026-09-15T14:35:00Z"
    assert len(dependency["content_sha256"]) == 64
    stored = repository.list_latest(
        environment_id="local",
        query_as_of=EVALUATION,
        include_terminal=True,
        include_blocked=True,
    )
    assert len(stored.items) == 1
    assert stored.items[0].symbol == "SPY"


def test_live_api_supplies_source_backed_context_for_every_horizon(monkeypatch, tmp_path):
    intraday_days = ("2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15")
    five_minute = [
        timestamp
        for day in intraday_days
        for timestamp in pd.date_range(
            f"{day}T09:30:00-04:00",
            periods=78 if day != "2026-09-15" else 15,
            freq="5min",
        )
    ]
    thirty_minute = [
        timestamp
        for day in intraday_days
        for timestamp in pd.date_range(
            f"{day}T09:30:00-04:00",
            periods=13 if day != "2026-09-15" else 3,
            freq="30min",
        )
    ]
    daily = pd.DatetimeIndex(
        pd.to_datetime(
            sorted(
                market_data_quality._daily_session_dates_for_range(
                    datetime(2026, 5, 1).date(), datetime(2026, 9, 15).date()
                )
            ),
            utc=True,
        )
    )

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return EVALUATION.astimezone(tz)

    class Provider:
        provider_name = "schwab"

        def get_intraday_bars(self, request):
            timestamps = thirty_minute if request.interval_minutes == 30 else five_minute
            return _bar_frame([timestamp.isoformat() for timestamp in timestamps])

        def get_daily_bars(self, request):
            return _bar_frame([timestamp.isoformat() for timestamp in daily])

    app = FastAPI()
    app.include_router(
        qx_v2.create_qx_v2_router(tmp_path, live_bar_provider=Provider())
    )
    monkeypatch.setattr(qx_v2, "datetime", Clock)
    monkeypatch.setattr(market_data_quality, "datetime", Clock)
    client = TestClient(app)

    expectations = {
        "5m": ("1h", "schwab:30m->1h", "1d", "schwab"),
        "1h": ("1d", "schwab", "1w", "schwab:1d->1w"),
        "1d": ("1w", "schwab:1d->1w", "1w", "schwab:1d->1w"),
    }
    for timeframe, (htf, htf_source, macro, macro_source) in expectations.items():
        response = client.post(
            "/api/v2/qx/evaluate/SPY",
            params={"timeframe": timeframe},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["htf_timeframe"] == htf
        assert payload["macro_timeframe"] == macro
        assert payload["data_dependencies"]["htf_bars"]["available"] is True
        assert payload["data_dependencies"]["htf_bars"]["source"] == htf_source
        assert payload["data_dependencies"]["macro_bars"]["available"] is True
        assert payload["data_dependencies"]["macro_bars"]["source"] == macro_source


def test_intraday_candidate_never_includes_daily_file(tmp_path):
    candidates = exact_cache_candidates(tmp_path, "SPY", "5m")
    assert candidates
    assert all(candidate.parent.name == "intraday" for candidate in candidates)
    assert all(candidate.name.endswith("_5m.csv") for candidate in candidates)


def test_daily_candidate_never_includes_intraday_file(tmp_path):
    candidates = exact_cache_candidates(tmp_path, "SPY", "daily")
    assert candidates
    assert all(candidate.parent == tmp_path for candidate in candidates)
    assert all(not candidate.name.endswith(("_1m.csv", "_5m.csv", "_15m.csv")) for candidate in candidates)


def test_active_daily_cache_cannot_satisfy_intraday_request(tmp_path):
    cache = tmp_path / "bars"
    active = tmp_path / "active"
    _write_bars(active / "SPY_1y.csv", ["2026-09-15"])

    result = load_audited_bars(cache, "SPY", "5m", EVALUATION, active)

    assert result.bars is None
    assert result.quality_report.status == MarketDataQualityStatus.UNAVAILABLE
    assert result.quality_report.reason_codes == ["REQUESTED_TIMEFRAME_UNAVAILABLE"]


def test_data_as_of_never_exceeds_evaluation_timestamp(tmp_path):
    path = tmp_path / "intraday" / "SPY_10d_5m.csv"
    timestamps = _complete_five_minute_timestamps()
    timestamps.append("2026-09-15T10:40:00-04:00")
    _write_bars(path, timestamps)

    result = load_audited_bars(tmp_path, "SPY", "5m", EVALUATION)

    assert result.quality_report.data_as_of is not None
    assert result.quality_report.data_as_of <= EVALUATION


def test_incomplete_current_candle_is_explicit_and_excluded(tmp_path):
    path = tmp_path / "intraday" / "SPY_10d_5m.csv"
    timestamps = _complete_five_minute_timestamps()
    timestamps.append("2026-09-15T10:40:00-04:00")
    _write_bars(path, timestamps)

    result = load_audited_bars(tmp_path, "SPY", "5m", EVALUATION)

    assert result.quality_report.status == MarketDataQualityStatus.PARTIAL
    assert result.quality_report.incomplete_candle_count == 1
    assert "INCOMPLETE_CURRENT_CANDLE_EXCLUDED" in result.quality_report.reason_codes
    assert result.bars is not None
    assert len(result.bars) == len(timestamps) - 1


def test_stale_required_bars_block_publication(tmp_path):
    path = tmp_path / "intraday" / "SPY_10d_5m.csv"
    _write_bars(path, _complete_five_minute_timestamps()[:-2])

    result = load_audited_bars(tmp_path, "SPY", "5m", EVALUATION)

    assert result.bars is None
    assert result.quality_report.status == MarketDataQualityStatus.BLOCKED
    assert result.quality_report.publication_allowed is False
    assert "STALE_BARS" in result.quality_report.reason_codes


def test_duplicate_out_of_order_and_missing_bars_are_reported(tmp_path):
    path = tmp_path / "intraday" / "SPY_10d_5m.csv"
    timestamps = _complete_five_minute_timestamps()
    timestamps.pop(4)
    timestamps.insert(7, timestamps[6])
    timestamps[9], timestamps[10] = timestamps[10], timestamps[9]
    _write_bars(path, timestamps)

    _, report = audit_cache_file(path, "SPY", "5m", EVALUATION)

    assert report.status == MarketDataQualityStatus.BLOCKED
    assert report.duplicate_count == 1
    assert report.out_of_order_count == 1
    assert report.missing_interval_count >= 1
    assert {"DUPLICATE_BARS", "OUT_OF_ORDER_BARS", "MISSING_INTRADAY_BARS"}.issubset(
        report.reason_codes
    )


def test_naive_intraday_timestamp_is_not_assumed_to_be_utc(tmp_path):
    path = tmp_path / "intraday" / "SPY_10d_5m.csv"
    _write_bars(path, ["2026-09-15 09:30:00", "2026-09-15 09:35:00"])

    result = load_audited_bars(tmp_path, "SPY", "5m", EVALUATION)

    assert result.bars is None
    assert "TIMESTAMP_TIMEZONE_UNAVAILABLE" in result.quality_report.reason_codes


def test_outside_regular_session_blocks_publication(tmp_path):
    path = tmp_path / "intraday" / "SPY_10d_5m.csv"
    timestamps = _complete_five_minute_timestamps()
    timestamps.insert(0, "2026-09-15T08:00:00-04:00")
    _write_bars(path, timestamps)

    result = load_audited_bars(tmp_path, "SPY", "5m", EVALUATION)

    assert result.bars is None
    assert result.quality_report.off_session_count == 1
    assert "OUTSIDE_REGULAR_SESSION" in result.quality_report.reason_codes


def test_missing_opening_interval_is_reported(tmp_path):
    path = tmp_path / "intraday" / "SPY_10d_5m.csv"
    _write_bars(path, _complete_five_minute_timestamps()[1:])

    result = load_audited_bars(tmp_path, "SPY", "5m", EVALUATION)

    assert result.bars is None
    assert result.quality_report.missing_interval_count == 1
    assert "MISSING_INTRADAY_BARS" in result.quality_report.reason_codes


def test_shifted_intraday_grid_is_rejected(tmp_path):
    path = tmp_path / "intraday" / "SPY_10d_5m.csv"
    timestamps = [
        timestamp.isoformat()
        for timestamp in pd.date_range(
            "2026-09-15T09:32:00-04:00",
            "2026-09-15T10:37:00-04:00",
            freq="5min",
        )
    ]
    _write_bars(path, timestamps)

    result = load_audited_bars(tmp_path, "SPY", "5m", EVALUATION)

    assert result.bars is None
    assert "TIMEFRAME_CADENCE_MISMATCH" in result.quality_report.reason_codes


def test_extra_off_grid_intraday_bar_is_rejected(tmp_path):
    path = tmp_path / "intraday" / "SPY_10d_5m.csv"
    timestamps = _complete_five_minute_timestamps()
    timestamps.append("2026-09-15T09:46:00-04:00")
    timestamps.sort()
    _write_bars(path, timestamps)

    result = load_audited_bars(tmp_path, "SPY", "5m", EVALUATION)

    assert result.bars is None
    assert "TIMEFRAME_CADENCE_MISMATCH" in result.quality_report.reason_codes


def test_daily_bar_visibility_uses_last_completed_session(tmp_path):
    path = tmp_path / "SPY_1y.csv"
    _write_bars(path, ["2026-09-14", "2026-09-15", "2026-09-16"])
    evaluation = datetime(2026, 9, 16, 16, 0, tzinfo=timezone.utc)

    result = load_audited_bars(tmp_path, "SPY", "daily", evaluation)

    assert result.quality_report.status == MarketDataQualityStatus.PARTIAL
    assert result.quality_report.publication_allowed is True
    assert result.quality_report.incomplete_candle_count == 1
    assert result.quality_report.data_as_of is not None
    assert result.quality_report.data_as_of <= evaluation


def test_future_daily_bar_blocks_instead_of_becoming_incomplete_candle(tmp_path):
    path = tmp_path / "SPY_1y.csv"
    _write_bars(path, ["2026-09-14", "2026-09-15", "2026-09-17"])
    evaluation = datetime(2026, 9, 16, 16, 0, tzinfo=timezone.utc)

    result = load_audited_bars(tmp_path, "SPY", "daily", evaluation)

    assert result.bars is None
    assert result.quality_report.status == MarketDataQualityStatus.BLOCKED
    assert result.quality_report.future_bar_count == 1
    assert result.quality_report.incomplete_candle_count == 0
    assert "FUTURE_BARS_EXCLUDED" in result.quality_report.reason_codes


def test_non_session_daily_label_blocks_publication(tmp_path):
    path = tmp_path / "SPY_1y.csv"
    _write_bars(path, ["2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16"])
    evaluation = datetime(2026, 9, 16, 16, 0, tzinfo=timezone.utc)

    result = load_audited_bars(tmp_path, "SPY", "daily", evaluation)

    assert result.bars is None
    assert "NON_SESSION_DAILY_BAR" in result.quality_report.reason_codes


def test_evaluation_date_weekend_bar_is_not_treated_as_incomplete(tmp_path):
    path = tmp_path / "SPY_1y.csv"
    _write_bars(path, ["2026-09-17", "2026-09-18", "2026-09-19"])
    evaluation = datetime(2026, 9, 19, 16, 0, tzinfo=timezone.utc)

    result = load_audited_bars(tmp_path, "SPY", "daily", evaluation)

    assert result.bars is None
    assert "NON_SESSION_DAILY_BAR" in result.quality_report.reason_codes


def test_non_session_daily_label_outside_recent_window_still_blocks(tmp_path):
    path = tmp_path / "SPY_1y.csv"
    sessions = pd.date_range("2026-07-01", "2026-09-15", freq="B")
    timestamps = [timestamp.date().isoformat() for timestamp in sessions]
    timestamps[0] = "2026-07-04"
    _write_bars(path, timestamps)
    evaluation = datetime(2026, 9, 16, 16, 0, tzinfo=timezone.utc)

    result = load_audited_bars(tmp_path, "SPY", "daily", evaluation)

    assert result.bars is None
    assert "NON_SESSION_DAILY_BAR" in result.quality_report.reason_codes


def test_missing_daily_session_outside_recent_window_still_blocks(tmp_path):
    path = tmp_path / "SPY_1y.csv"
    sessions = pd.date_range("2026-07-01", "2026-09-15", freq="B")
    timestamps = [timestamp.date().isoformat() for timestamp in sessions]
    timestamps.pop(3)
    _write_bars(path, timestamps)
    evaluation = datetime(2026, 9, 16, 16, 0, tzinfo=timezone.utc)

    result = load_audited_bars(tmp_path, "SPY", "daily", evaluation)

    assert result.bars is None
    assert "MISSING_DAILY_BARS" in result.quality_report.reason_codes


def test_intraday_cache_spanning_dst_offsets_normalizes_to_utc(tmp_path):
    path = tmp_path / "intraday" / "SPY_10d_5m.csv"
    timestamps = [
        timestamp.isoformat()
        for day in ("2026-10-30T09:30:00-04:00", "2026-11-02T09:30:00-05:00")
        for timestamp in pd.date_range(day, periods=78, freq="5min")
    ]
    _write_bars(path, timestamps)
    evaluation = datetime(2026, 11, 2, 21, 5, tzinfo=timezone.utc)

    result = load_audited_bars(tmp_path, "SPY", "5m", evaluation)

    assert result.bars is not None
    assert result.quality_report.status == MarketDataQualityStatus.PASS
    assert result.quality_report.timestamp_timezone == "UTC"


def test_invalid_ohlcv_is_reported_without_normalization_hiding_it(tmp_path):
    path = tmp_path / "intraday" / "SPY_10d_5m.csv"
    _write_bars(path, _complete_five_minute_timestamps())
    frame = pd.read_csv(path)
    frame.loc[2, "close"] = None
    frame.to_csv(path, index=False)

    result = load_audited_bars(tmp_path, "SPY", "5m", EVALUATION)

    assert result.bars is None
    assert result.quality_report.invalid_ohlcv_count == 1
    assert "INVALID_OHLCV" in result.quality_report.reason_codes


def test_api_blocks_when_required_bar_cache_is_stale(tmp_path):
    cache = tmp_path / "bars"
    path = cache / "intraday" / "SPY_10d_5m.csv"
    _write_bars(path, _complete_five_minute_timestamps()[:-2])
    client = TestClient(
        web.create_app(
            tmp_path / "qx.db",
            cache,
            configure_canonical_providers=False,
        )
    )

    response = client.post(
        "/api/v2/qx/evaluate/SPY",
        params={"timeframe": "5m", "evaluation_timestamp": EVALUATION.isoformat()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_lifecycle_state"] == "BLOCKED"
    assert payload["data_dependencies"]["bars"]["quality_status"] == "BLOCKED"
    assert "STALE_BARS" in payload["data_dependencies"]["bars"]["quality_reason_codes"]
