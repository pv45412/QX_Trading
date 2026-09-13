from streamlit.testing.v1 import AppTest

from qx.ui.pages.spx_dashboard import futures_decision_state


def test_futures_workspace_starts_with_requested_primary_tabs():
    app = AppTest.from_string('''
import streamlit as st
from qx.ui.pages.spx_dashboard import render_spx_dashboard_page
render_spx_dashboard_page(st)
''').run(timeout=30)

    assert not app.exception
    assert [tab.label for tab in app.tabs[:3]] == ["SPX Intraday", "SPX Calendars", "MAG11 Gamma Trends"]
    assert any("Preferred calendar structure" in item.value for item in app.markdown)
    assert any("Aggregate gamma state" in item.value for item in app.markdown)


def test_futures_layout_groups_reference_data_and_limitations():
    app = AppTest.from_string('''
import streamlit as st
from qx.market.spx_dashboard import build_spx_dashboard
from qx.ui.pages.spx_dashboard import _render_dashboard
from tests.unit.test_spx_dashboard import StaticProvider, _bars
symbols = ["SPY", "QQQ", "IWM", "ES=F", "NQ=F", "YM=F", "RTY=F", "ZN=F", "ZB=F", "DX-Y.NYB", "CL=F", "GC=F", "^VIX"]
dashboard = build_spx_dashboard(StaticProvider({symbol: _bars(100., .1) for symbol in symbols}))
_render_dashboard(st, dashboard)
''').run(timeout=30)
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Levels & Scenarios", "Cross-Market", "Playbook", "Data & Notes"]
    assert any("not live trade signals" in item.value for item in app.warning)
    assert len(app.dataframe[0].value.columns) == 6
    assert any(item.label == "Unverified ES reference comparison" for item in app.expander)
    assert any("Intraday confirmation unavailable" in item.value for item in app.markdown)
    assert any("Source attribution" in item.value and "unknown" in item.value for item in app.markdown)
    assert len(app.get("plotly_chart")) == 1
    evidence = app.table[0].value
    assert evidence.index.tolist() == ["ES=F", "NQ=F"]
    assert evidence["Source"].tolist() == ["unknown", "unknown"]
    assert len(app.get("download_button")) == 1

    assert any(item.label == "Decision reference" for item in app.selectbox)


def test_futures_decision_state_requires_complete_verified_evidence():
    assert futures_decision_state(None)[0] == "Evidence required"
    assert futures_decision_state({"rows": []})[0] == "Evidence unavailable"
    assert futures_decision_state({"rows": [{"requested_symbol": "ES=F"}]})[0] == "Evidence incomplete"

    stale = {
        "rows": [
            {"requested_symbol": "ES=F", "quote_status": "unverified_or_stale"},
            {"requested_symbol": "NQ=F", "quote_status": "fresh_at_check"},
        ]
    }
    assert futures_decision_state(stale)[0] == "Preview only"

    fresh_but_unaligned = {
        "rows": [
            {"requested_symbol": "ES=F", "quote_status": "fresh_at_check", "live_signal_eligible": False},
            {"requested_symbol": "NQ=F", "quote_status": "fresh_at_check", "live_signal_eligible": False},
        ]
    }
    assert futures_decision_state(fresh_but_unaligned)[0] == "Preview only"


def test_decision_reference_label_keeps_symbol_state_and_name_visible():
    from qx.ui.pages.spx_dashboard import _decision_reference_label

    class Row:
        symbol = "ES=F"
        name = "S&P 500 Futures"
        timing_state = "Wait for confirmation"

    assert _decision_reference_label(Row()) == "ES=F | S&P 500 Futures | Wait for confirmation"


def test_evidence_gate_count_is_zero_without_a_contract_report():
    from qx.ui.pages.spx_dashboard import _evidence_gate_count

    assert _evidence_gate_count(None) == (0, 4)
    assert _evidence_gate_count({"rows": []}) == (0, 4)


def test_evidence_gate_count_does_not_treat_missing_continuity_as_ready():
    from qx.ui.pages.spx_dashboard import _evidence_gate_count

    report = {"rows": [
        {"requested_symbol": "ES=F", "quote_status": "fresh_at_check",
         "history_status": "provider_contract_matched", "continuous_cache_comparable": False,
         "cash_close_synchronized": False},
        {"requested_symbol": "NQ=F", "quote_status": "fresh_at_check",
         "history_status": "provider_contract_matched", "continuous_cache_comparable": False,
         "cash_close_synchronized": False},
    ]}
    assert _evidence_gate_count(report) == (2, 4)


def test_data_foundation_distinguishes_ready_context_from_missing_intraday_feed():
    from qx.ui.pages.spx_dashboard import futures_facet_readiness

    report = {"rows": [
        {"requested_symbol": "ES=F", "quote_status": "fresh_at_check",
         "history_status": "provider_contract_matched", "continuous_cache_comparable": True,
         "cash_close_synchronized": True},
        {"requested_symbol": "NQ=F", "quote_status": "fresh_at_check",
         "history_status": "provider_contract_matched", "continuous_cache_comparable": True,
         "cash_close_synchronized": True},
    ]}
    readiness = {item.key: item for item in futures_facet_readiness(report)}
    assert readiness["futures_context"].status == "ready"
    assert readiness["intraday_structure"].status == "blocked"
    assert readiness["intraday_structure"].missing_artifacts == ("five_minute_bars",)


def test_empty_decision_preview_explains_that_live_refresh_is_explicit():
    app = AppTest.from_string('''
import streamlit as st
from qx.ui.pages.spx_dashboard import _render_empty_decision_preview
_render_empty_decision_preview(st)
''').run()

    assert not app.exception
    assert any("live refresh stays explicit" in item.value for item in app.markdown)


def test_reference_cards_expose_fallback_and_keep_missing_instrument_visible():
    app = AppTest.from_string('''
import streamlit as st
from qx.market.spx_dashboard import build_spx_dashboard
from qx.ui.pages.spx_dashboard import _render_dashboard
from tests.unit.test_futures_daily_evidence import sourced_bars
from tests.unit.test_spx_dashboard import StaticProvider
bars = sourced_bars()
_render_dashboard(st, build_spx_dashboard(StaticProvider({"SPY": bars, "ES=F": bars})))
''').run(timeout=30)
    assert not app.exception
    assert any("yfinance · fallback" in item.value for item in app.markdown)
    assert app.table[0].value.loc["NQ=F", "Status"] == "unavailable"
    assert any("relative performance is withheld" in item.value for item in app.markdown)



def test_missing_history_renders_empty_chart_without_invented_candles():
    app = AppTest.from_string('''
import streamlit as st
from qx.market.spx_dashboard import build_spx_dashboard
from qx.ui.pages.spx_dashboard import _render_dashboard
from tests.unit.test_spx_dashboard import StaticProvider, _bars
_render_dashboard(st, build_spx_dashboard(StaticProvider({"SPY": _bars(100., .1)})))
''').run(timeout=30)
    assert not app.exception
    assert len(app.get("plotly_chart")) == 0
    assert any("Daily history unavailable" in item.value for item in app.markdown)
