"""Backward compatibility layer re-exporting SPX Calendar & Volatility Term Structure Engine.

Canonical domain package: qx.options.calendar
"""

from qx.options.calendar import (
    CalendarSpreadIdea,
    ExpirationRow,
    IvTermStructure,
    SpxCalendarDashboard,
    analyze_iv_term_structure,
    build_spx_calendar_dashboard,
    generate_spx_calendars,
)

__all__ = [
    "CalendarSpreadIdea",
    "ExpirationRow",
    "IvTermStructure",
    "SpxCalendarDashboard",
    "analyze_iv_term_structure",
    "build_spx_calendar_dashboard",
    "generate_spx_calendars",
]
