import pandas as pd

from qx.ui.sector_board import ranked_sectors, excess_cell_style


def test_ranking_uses_relative_return_and_keeps_missing_last() -> None:
    source = pd.DataFrame({"etf": ["A", "B", "C"], "relative_20d": [0.01, float("nan"), 0.04]})
    assert ranked_sectors(source)["etf"].tolist() == ["C", "A", "B"]
    assert source["etf"].tolist() == ["A", "B", "C"]


def test_heatmap_keeps_missing_and_zero_neutral():
    assert excess_cell_style(float("nan")) == ""
    assert excess_cell_style(0) == ""
    assert excess_cell_style(None) == ""
    assert "#146448" in excess_cell_style(1.5)
    assert "#a22b3c" in excess_cell_style(-1.5)
