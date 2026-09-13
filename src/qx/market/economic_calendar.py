"""Public, source-attributed scheduled economic events.

Only publisher supplied timing and title are represented.  Consensus values,
surprises, and market impact require separate attributable inputs and are not
inferred here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

import requests


BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
_EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class ScheduledEvent:
    source: str
    source_url: str
    title: str
    scheduled_at: datetime
    retrieved_at: datetime


class CalendarUnavailable(ValueError):
    pass


def fetch_bls_events(
    *,
    now: datetime | None = None,
    http_get: Callable[..., object] = requests.get,
    timeout_seconds: float = 10,
) -> tuple[ScheduledEvent, ...]:
    """Fetch and parse BLS's public ICS schedule without filling missing fields."""
    retrieved_at = now or datetime.now(timezone.utc)
    if retrieved_at.utcoffset() is None:
        raise CalendarUnavailable("Calendar retrieval requires an aware clock")
    try:
        response = http_get(
            BLS_ICS_URL,
            timeout=timeout_seconds,
            headers={"User-Agent": "SCANNER market-research client/0.1"},
        )
        raise_for_status = getattr(response, "raise_for_status", None)
        text = getattr(response, "text", None)
        if not callable(raise_for_status) or not isinstance(text, str):
            raise ValueError("Invalid calendar response")
        raise_for_status()
        return parse_bls_ics(text, retrieved_at=retrieved_at)
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise CalendarUnavailable("BLS release calendar unavailable") from exc


def parse_bls_ics(content: str, *, retrieved_at: datetime) -> tuple[ScheduledEvent, ...]:
    """Parse a conservative subset of iCalendar needed for the BLS release feed."""
    if retrieved_at.utcoffset() is None:
        raise CalendarUnavailable("Calendar retrieval requires an aware clock")
    lines = _unfold(content)
    records: list[ScheduledEvent] = []
    current: dict[str, str] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            if current is not None:
                event = _event_from_fields(current, retrieved_at)
                if event is not None:
                    records.append(event)
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key.split(";", 1)[0]] = value.strip()
    unique = {(event.scheduled_at, event.title): event for event in records}
    return tuple(sorted(unique.values(), key=lambda event: (event.scheduled_at, event.title)))


def _unfold(content: str) -> list[str]:
    if not isinstance(content, str) or not content.strip():
        raise CalendarUnavailable("Empty calendar response")
    lines: list[str] = []
    for raw in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw.strip())
    return lines


def _event_from_fields(fields: dict[str, str], retrieved_at: datetime) -> ScheduledEvent | None:
    title = fields.get("SUMMARY", "").replace("\\,", ",").replace("\\n", " ").strip()
    raw_time = fields.get("DTSTART")
    if not title or not raw_time:
        return None
    try:
        if raw_time.endswith("Z"):
            scheduled = datetime.strptime(raw_time, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        elif "T" in raw_time:
            scheduled = datetime.strptime(raw_time, "%Y%m%dT%H%M%S").replace(tzinfo=_EASTERN)
        else:
            # A date-only release has no known clock time; do not convert it into an intraday event.
            return None
    except ValueError:
        return None
    return ScheduledEvent(
        source="bls",
        source_url=BLS_ICS_URL,
        title=title,
        scheduled_at=scheduled,
        retrieved_at=retrieved_at,
    )
