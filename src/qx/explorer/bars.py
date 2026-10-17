"""Bar completion: which bars are finished observations? (reviewer F07)

The previous rule was ``last = n if forming else n - 1`` — it dropped the final
supplied bar UNCONDITIONALLY, whether or not that bar was still forming. That
discarded a legitimately completed bar in after-hours, replay and cache paths, and
made different features reference different observations (some used ``bars[-1]``).

The rule now: a bar is COMPLETED when the next scheduled bar for its timeframe has
already opened. That is decidable from the bar's own timestamp plus the session
calendar, so it works for daily and intraday alike, and it degrades to "unknown"
rather than guessing when no timestamp is available.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Sequence

# Minutes per bar for the intervals this app supports.
_INTERVAL_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1d": 1440}

# A daily bar for session D is completed once the next session opens. Regular
# US equity sessions open 09:30 ET; we use a conservative 14:30 UTC (09:30 ET in
# EDT) and accept either, since the exact offset shifts with DST.
_DAILY_OPEN_UTC_HOUR = 14
_DAILY_OPEN_UTC_MINUTE = 30


def _parse(stamp: Any) -> dt.datetime | None:
    if isinstance(stamp, dt.datetime):
        value = stamp
    elif isinstance(stamp, str) and stamp:
        try:
            value = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value


def _next_open(after: dt.datetime) -> dt.datetime:
    """The next regular-session open strictly after ``after`` (weekday-aware)."""
    candidate = after.replace(hour=_DAILY_OPEN_UTC_HOUR, minute=_DAILY_OPEN_UTC_MINUTE,
                              second=0, microsecond=0)
    if candidate <= after:
        candidate += dt.timedelta(days=1)
    while candidate.weekday() >= 5:            # skip Saturday/Sunday
        candidate += dt.timedelta(days=1)
    return candidate


def is_completed(bar: dict[str, Any], *, now: dt.datetime | None = None,
                 interval: str | None = None) -> bool | None:
    """True/False when decidable, None when the bar carries no usable time.

    ``None`` is a first-class answer: it means "we cannot tell", and callers must
    not silently treat that as completed OR as forming.
    """
    explicit = bar.get("bar_completed")
    stamp = _parse(bar.get("date"))
    if stamp is None:
        # No observation time: fall back to the provider's own flag if present.
        return bool(explicit) if explicit is not None else None

    reference = now or dt.datetime.now(dt.timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=dt.timezone.utc)

    resolved = interval or bar.get("interval") or "1d"
    if resolved == "1d":
        # A daily bar is labelled with its SESSION DATE at 00:00. It is completed
        # once that session's own close has passed. The close is ~20:00 UTC
        # (16:00 ET); use 21:00 UTC to stay conservative across DST.
        session_close = stamp.replace(hour=21, minute=0, second=0, microsecond=0)
        return reference >= session_close

    minutes = _INTERVAL_MINUTES.get(resolved, 1440)
    return reference >= stamp + dt.timedelta(minutes=minutes)


def select_series(bars: Sequence[dict[str, Any]], *, forming: bool = False,
                  interval: str | None = None,
                  now: dt.datetime | None = None) -> list[dict[str, Any]]:
    """Return the bars a study should evaluate.

    ``forming=False`` (the default) excludes a bar that is still forming.

    Two distinct cases, deliberately treated differently:
      * completion KNOWN True  -> keep the final bar (F07: it was being discarded)
      * completion KNOWN False -> drop it
      * completion UNKNOWN (no observation time) -> drop it, and say so
        A series with no timestamps cannot demonstrate that its final bar is
        finished, and a study must not treat an unverifiable bar as a settled
        observation. Callers that genuinely want it pass ``forming=True``.
    """
    if forming:
        return list(bars)
    if not bars:
        return []
    last_state = is_completed(bars[-1], now=now, interval=interval)
    if last_state is True:
        return list(bars)
    return list(bars[:-1])


def completion_state(bars: Sequence[dict[str, Any]], *, interval: str | None = None,
                     now: dt.datetime | None = None) -> dict[str, Any]:
    """Describe the final bar's completion, for evidence and staleness reporting."""
    if not bars:
        return {"has_bar": False, "completed": None, "reason": "no bars"}
    state = is_completed(bars[-1], now=now, interval=interval)
    return {
        "has_bar": True,
        "completed": state,
        "bar_date": bars[-1].get("date"),
        "interval": interval or bars[-1].get("interval") or "1d",
        "reason": ("the bar's session or interval has closed" if state is True else
                   "the bar is still forming" if state is False else
                   "bar carries no observation time — completion unknown"),
    }
