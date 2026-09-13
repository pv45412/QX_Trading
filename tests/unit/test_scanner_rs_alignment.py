import pandas as pd
import pytest

from qx.core.engine import ScannerEngine, _return_window
from tests.unit.test_engine import BenchmarkProvider


@pytest.mark.parametrize("mode", ["shift", "short", "nan", "zero", "reverse"])
def test_invalid_benchmark_withholds_rs_only(mode):
    class Provider(BenchmarkProvider):
        def get_daily_bars(self, request):
            bars = super().get_daily_bars(request)
            if request.symbol == "SPY":
                if mode == "shift":
                    bars.index = bars.index + 1
                elif mode == "short":
                    bars = bars.tail(20)
                elif mode in {"nan", "zero"}:
                    bars.loc[bars.index[-1], "close"] = float("nan") if mode == "nan" else 0
                else:
                    bars = bars.iloc[::-1]
            return bars
    result = ScannerEngine(Provider()).scan_symbols_sequential(["GOOD"])
    assert result.failed_symbols == 0
    assert result.candidates[0].metrics.rs_status == "Not checked"


def test_return_window_validates_all_prices():
    bars = pd.DataFrame({"close": [100.] * 21}, index=pd.date_range("2026-01-01", periods=21))
    assert _return_window(bars)[1] == 0
    bars.iloc[10, 0] = float("inf")
    assert _return_window(bars) is None
