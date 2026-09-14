"""Unit tests for SPX Calendar & Volatility Term Structure Engine."""

import pytest
from qx.options.calendar import (
    analyze_iv_term_structure,
    build_spx_calendar_dashboard,
    generate_spx_calendars,
)
from qx.options.calendar_engine import (
    CalendarSpreadIdea as ReexportedIdea,
    build_spx_calendar_dashboard as reexported_builder,
)


def test_iv_term_structure_contango_slope():
    """Verify IV term structure contango slope and differential calculations."""
    ts = analyze_iv_term_structure(volatility_annual=0.16)
    assert ts.front_leg_dte == 1
    assert ts.back_leg_dte == 4
    assert ts.front_leg_iv > ts.back_leg_iv
    assert ts.iv_differential_pct > 0.0
    assert "Contango" in ts.iv_slope


def test_spx_calendar_ideas_generation():
    """Verify generation of 3 core SPX calendar spread trade setups."""
    spot = 5800.0
    ideas = generate_spx_calendars(spot)

    assert len(ideas) == 3
    names = [idea.name for idea in ideas]
    assert "Weekend Theta Capture Calendar" in names[0]
    assert "Dealer Call Wall Pin Calendar" in names[1]
    assert "Dealer Put Wall Support Calendar" in names[2]

    for idea in ideas:
        assert idea.net_debit > 0.0
        assert idea.max_profit > 0.0
        assert idea.win_probability_pct > 70.0


def test_spx_calendar_dashboard_builder():
    """Verify complete SPX Calendar Spread dashboard state builder."""
    dashboard = build_spx_calendar_dashboard(symbol="SPX", spot_price=5750.0)

    assert dashboard.symbol == "SPX"
    assert dashboard.current_price == 5750.0
    assert len(dashboard.calendars) == 3
    assert len(dashboard.expiry_comparison) > 0
    assert dashboard.contracts_with_open_interest > 0


def test_backward_compatibility_reexport():
    """Verify backward-compatibility re-export layer in qx.options.calendar_engine."""
    dashboard = reexported_builder(symbol="SPX", spot_price=5750.0)
    assert dashboard.symbol == "SPX"
    assert isinstance(dashboard.calendars[0], ReexportedIdea)
