from datetime import datetime, timezone

import pytest
import requests

from qx.market.economic_calendar import CalendarUnavailable, fetch_bls_events, parse_bls_ics


NOW = datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc)
ICS = """BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20260915T083000\nSUMMARY:Consumer Price Index\\, August 2026\nEND:VEVENT\nBEGIN:VEVENT\nDTSTART:20260915T083000\nSUMMARY:Consumer Price Index\\, August 2026\nEND:VEVENT\nBEGIN:VEVENT\nDTSTART;VALUE=DATE:20260916\nSUMMARY:Date only event\nEND:VEVENT\nEND:VCALENDAR\n"""


def test_parses_deduplicated_eastern_timestamped_bls_events():
    events = parse_bls_ics(ICS, retrieved_at=NOW)
    assert len(events) == 1
    event = events[0]
    assert event.title == "Consumer Price Index, August 2026"
    assert event.scheduled_at.isoformat() == "2026-09-15T08:30:00-04:00"
    assert event.retrieved_at == NOW


def test_rejects_naive_retrieval_clock_and_empty_calendar():
    with pytest.raises(CalendarUnavailable, match="aware"):
        parse_bls_ics(ICS, retrieved_at=NOW.replace(tzinfo=None))
    with pytest.raises(CalendarUnavailable, match="Empty"):
        parse_bls_ics("", retrieved_at=NOW)


def test_fetches_only_valid_http_calendar_payload():
    class Response:
        text = ICS

        def raise_for_status(self):
            return None

    assert fetch_bls_events(now=NOW, http_get=lambda *_args, **_kwargs: Response())[0].source == "bls"

    class BadResponse:
        text = "not a calendar"

        def raise_for_status(self):
            raise requests.HTTPError("bad")

    with pytest.raises(CalendarUnavailable, match="unavailable"):
        fetch_bls_events(now=NOW, http_get=lambda *_args, **_kwargs: BadResponse())
