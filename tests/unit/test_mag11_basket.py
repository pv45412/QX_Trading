import pytest
from streamlit.testing.v1 import AppTest

from qx.ui.pages.spx_dashboard import _parse_mag11_basket


def test_mag11_basket_requires_exactly_eleven_distinct_symbols() -> None:
    symbols = "\n".join(f"S{index}" for index in range(11))
    assert _parse_mag11_basket(symbols) == tuple(f"S{index}" for index in range(11))
    with pytest.raises(ValueError, match="exactly 11"):
        _parse_mag11_basket("AAPL\nMSFT")
    with pytest.raises(ValueError, match="distinct"):
        _parse_mag11_basket("\n".join(["AAPL"] * 11))


def test_mag11_basket_is_empty_until_the_user_defines_one() -> None:
    assert _parse_mag11_basket("") == ()


def test_mag11_workspace_exposes_background_daily_trend_action() -> None:
    basket = "\n".join(f"S{index}" for index in range(11))
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.pages.spx_dashboard import _render_mag11_gamma_workspace\n"
        "_render_mag11_gamma_workspace(st)\n"
    ).run()
    app.text_area[0].set_value(basket).run()
    assert not app.exception
    assert any(button.label == "Load daily trends" for button in app.button)
    assert any(select.label == "Trend history" for select in app.selectbox)
