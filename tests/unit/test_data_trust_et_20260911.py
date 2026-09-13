from datetime import date, datetime

import pandas as pd
import pytest

from qx.ui.formatting import display_frame, format_timestamp
from qx.ui.pages.morning_report import _format_run_time


@pytest.mark.parametrize(("value", "expected"), [
    ("2026-09-11T11:52:00Z", "Sep 11, 2026 07:52 AM EDT"),
    ("2026-09-11T11:52:00", "Sep 11, 2026 07:52 AM EDT"),
    ("2026-09-11T07:52:00-04:00", "Sep 11, 2026 07:52 AM EDT"),
    ("2026-01-11T11:52:00+00:00", "Jan 11, 2026 06:52 AM EST"),
    ("2026-03-08T06:59:00Z", "Mar 08, 2026 01:59 AM EST"),
    ("2026-03-08T07:00:00Z", "Mar 08, 2026 03:00 AM EDT"),
    ("2026-11-01T05:30:00Z", "Nov 01, 2026 01:30 AM EDT"),
    ("2026-11-01T06:30:00Z", "Nov 01, 2026 01:30 AM EST"),
    ("2026-09-11T00:00:00Z", "Sep 10, 2026 08:00 PM EDT"),
    ("2026-09-11", "Sep 11, 2026"),
    (date(2026, 9, 11), "Sep 11, 2026"),
    (datetime(2026, 9, 11, 11, 52), "Sep 11, 2026 07:52 AM EDT"),
    (None, "n/a"),
    (pd.NaT, "n/a"),
    ("not a timestamp", "not a timestamp"),
])
def test_explicit_et_and_date_labels(value, expected):
    assert format_timestamp(value) == expected
    assert _format_run_time(value) == expected


def test_timestamp_columns_share_formatter_without_changing_session_dates():
    columns = ["created_at", "saved_at", "retrieved_at", "modified_at", "session_date"]
    frame = pd.DataFrame([{**dict.fromkeys(columns[:-1], "2026-09-11T11:52:00Z"),
                           "session_date": "2026-09-11"}])
    result = display_frame(frame, columns=columns)
    assert all(value == "Sep 11, 2026 07:52 AM EDT" for value in result.iloc[0, :-1])
    assert result.iloc[0, -1] == "2026-09-11"
