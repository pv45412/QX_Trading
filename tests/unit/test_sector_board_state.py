from streamlit.testing.v1 import AppTest


def app():
    import pandas as pd
    import streamlit as st
    from qx.ui.sector_board import render_sector_board
    frame = pd.DataFrame([
        {"etf": "XLK", "sector": "Technology", "relative_5d": .01, "relative_20d": .04, "relative_60d": .02},
        {"etf": "XLE", "sector": "Energy", "relative_5d": .05, "relative_20d": .01, "relative_60d": .03},
    ])
    render_sector_board(st, frame, pd.DataFrame())


def test_ranking_filters_and_selection_reconcile():
    at = AppTest.from_function(app).run()
    assert not at.exception
    assert at.selectbox(key="sector_board_symbol").value == "XLK"
    at.text_input(key="sector_board_search").set_value("energy").run()
    assert not at.exception
    assert at.selectbox(key="sector_board_symbol").value == "XLE"
    assert len(at.dataframe[0].value) == 1
    at.text_input(key="sector_board_search").set_value("[").run()
    assert not at.exception
    assert at.info[0].value == "No matching sectors."


def test_window_changes_numeric_order_and_legacy_evidence_warning():
    at = AppTest.from_function(app).run()
    at.selectbox(key="sector_board_window").select("5D").run()
    assert not at.exception
    assert at.dataframe[0].value.iloc[0]["ETF"] == "XLE"
    assert at.dataframe[0].value["5D vs SPY (pp)"].dtype.kind == "f"
    assert "legacy snapshot" in at.warning[0].value
