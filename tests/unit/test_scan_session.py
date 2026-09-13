import pandas as pd

from qx.core.session import ScanSession
from qx.data.providers import MarketDataProvider
from qx.models.market import BarDataRequest


class StaticProvider:
    def __init__(self, bars: pd.DataFrame) -> None:
        self.bars = bars

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        return self.bars


def test_scan_session_returns_ranked_candidates() -> None:
    provider: MarketDataProvider = StaticProvider(_rectangle_bars())

    result = ScanSession(provider=provider).run(["TEST"])

    assert result.total_symbols == 1
    assert result.candidates[0].symbol == "TEST"
    assert result.candidates[0].score > 0.8


def _rectangle_bars() -> pd.DataFrame:
    rows: list[dict[str, float]] = []

    for index in range(160):
        close = 20 + index * 0.07
        rows.append(
            {
                "open": close - 0.08,
                "high": close + 0.20,
                "low": close - 0.20,
                "close": close,
                "volume": 900_000,
            }
        )

    wave = [30.1, 31.2, 32.7, 31.5, 30.2, 31.0, 32.8, 31.4] * 5
    for index, close in enumerate(wave):
        body_direction = 1 if index % 3 != 0 else -1
        open_price = close - (0.18 * body_direction)
        recent = index >= 35
        rows.append(
            {
                "open": open_price,
                "high": close + (0.10 if recent else 0.28),
                "low": close - (0.10 if recent else 0.28),
                "close": close,
                "volume": 750_000 - index * 9_000,
            }
        )

    rows.append(
        {
            "open": 32.35,
            "high": 32.82,
            "low": 32.25,
            "close": 32.75,
            "volume": 310_000,
        }
    )
    return pd.DataFrame(rows)
