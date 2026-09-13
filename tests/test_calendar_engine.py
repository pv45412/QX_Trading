from qx.options.calendar_engine import build_spx_calendar_dashboard, SpxCalendarDashboard, CalendarSpreadIdea


def test_build_spx_calendar_dashboard_defaults():
    dashboard = build_spx_calendar_dashboard()
    assert isinstance(dashboard, SpxCalendarDashboard)
    assert dashboard.symbol == "SPX"
    assert dashboard.current_price == 7656.98
    assert len(dashboard.calendars) == 3
    assert dashboard.iv_term_structure.front_leg_dte == 1
    assert dashboard.iv_term_structure.back_leg_dte == 4


def test_build_spx_calendar_dashboard_custom_price():
    dashboard = build_spx_calendar_dashboard(symbol="spx", spot_price=5000.0)
    assert dashboard.current_price == 5000.0
    for cal in dashboard.calendars:
        assert isinstance(cal, CalendarSpreadIdea)
        assert cal.net_debit > 0
        assert cal.max_profit > 0
        assert cal.win_probability_pct > 50.0
