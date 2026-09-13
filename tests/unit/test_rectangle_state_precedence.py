import pandas as pd
import pytest

from qx.models.scan import RectangleScanParameters
from qx.patterns.rectangle import _breakout_status, _is_near_resistance, analyze_rectangle


@pytest.mark.parametrize("distance", [0.001, 0.02, 0.04, 0.10])
def test_below_support_cannot_be_ready(distance):
    assert _breakout_status(-0.01, distance) == "Below Support"
    assert not _is_near_resistance(-0.01, distance, RectangleScanParameters(max_resistance_distance_pct=0.05))


@pytest.mark.parametrize("distance", [0.0, 0.05])
def test_zero_width_box_is_not_ready(distance):
    bars = pd.DataFrame({"open": [100.] * 220, "high": [100.] * 220,
                         "low": [100.] * 220, "close": [100.] * 220, "volume": [1000000.] * 220})
    candidate = analyze_rectangle("FLAT", bars, RectangleScanParameters(max_resistance_distance_pct=distance))
    assert not candidate.passed
    assert candidate.metrics.breakout_status == "Invalid Range"
    assert not next(rule for rule in candidate.rules if rule.name == "near_resistance").passed


@pytest.mark.parametrize("position,distance,status", [(1.01, -0.01, "Breakout"),
                                                       (0.95, 0.02, "Ready"),
                                                       (0.86, 0.04, "Near Breakout"),
                                                       (0.4, 0.08, "Inside Box")])
def test_valid_states_unchanged(position, distance, status):
    assert _breakout_status(position, distance) == status
