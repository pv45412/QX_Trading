from datetime import datetime, timedelta

from qx.brokers.schwab.timing import SchwabEmaTimingProvider


class FakeTimingClient:
    def get(self, path: str, *, params: dict[str, object] | None = None) -> dict[str, object]:
        assert path == "/marketdata/v1/pricehistory"
        assert params is not None
        frequency_type = str(params["frequencyType"])
        frequency = int(params["frequency"])
        if frequency_type == "daily":
            return {"candles": _candles(90, step_minutes=1440)}
        if frequency_type == "minute" and frequency == 30:
            return {"candles": _candles(180, step_minutes=30)}
        if frequency_type == "minute" and frequency == 15:
            return {"candles": _candles(90, step_minutes=15)}
        raise AssertionError(f"Unexpected params: {params}")


def test_schwab_timing_provider_builds_fractal_ema_snapshot() -> None:
    provider = SchwabEmaTimingProvider(FakeTimingClient())  # type: ignore[arg-type]

    snapshot = provider.get_timing("SPY")

    assert snapshot.score >= 0.80
    assert snapshot.label == "Aligned"
    assert "H50 held" in snapshot.alignment
    assert snapshot.trigger == "Trigger active"


def _candles(count: int, *, step_minutes: int) -> list[dict[str, float | int]]:
    start = datetime(2026, 1, 1, 9, 30)
    rows: list[dict[str, float | int]] = []
    for index in range(count):
        close = 100.0 + index
        moment = start + timedelta(minutes=step_minutes * index)
        rows.append(
            {
                "datetime": int(moment.timestamp() * 1000),
                "open": close - 0.25,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1_000_000 + index,
            }
        )
    return rows
