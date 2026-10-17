"""Display time formatting in EXCHANGE time (US/Eastern), not UTC.

Timestamps travel as ISO-8601 UTC strings. Showing them raw makes a trader convert
in their head, and makes a 14:33 bar look like "14:33" when the market has only
been open 33 minutes. This module renders them in market time with an explicit
label, and never guesses when a value is missing or unparseable.

DST is handled by ``zoneinfo`` so EST/EDT switch automatically.
"""
from __future__ import annotations

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

EXCHANGE_TZ = ZoneInfo("America/New_York")
EXCHANGE_LABEL = "ET"


def exchange_label(now: dt.datetime | None = None) -> str:
    """'ET' always; kept explicit so callers do not hardcode an abbreviation."""
    return EXCHANGE_LABEL


def to_exchange(value: Any) -> dt.datetime | None:
    """Parse an ISO-ish timestamp and convert to exchange time. None if unusable."""
    if value is None or value == "":
        return None
    moment: dt.datetime | None
    if isinstance(value, dt.datetime):
        moment = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            moment = dt.datetime.fromtimestamp(float(value), tz=dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            moment = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            # A bare HH:MM:SS is assumed to be UTC only when it looks like one.
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    moment = dt.datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(EXCHANGE_TZ)


def hhmmss(value: Any, *, fallback: str = "—") -> str:
    """Clock time in exchange time, e.g. '09:47:12'. No timezone suffix."""
    moment = to_exchange(value)
    return moment.strftime("%H:%M:%S") if moment else fallback


def hhmm(value: Any, *, fallback: str = "—") -> str:
    moment = to_exchange(value)
    return moment.strftime("%H:%M") if moment else fallback


def stamp(value: Any, *, fallback: str = "time unavailable") -> str:
    """'09:47:12 ET' — the form the UI should show."""
    moment = to_exchange(value)
    if moment is None:
        return fallback
    return f"{moment.strftime('%H:%M:%S')} {EXCHANGE_LABEL}"


def stamp_short(value: Any, *, fallback: str = "—") -> str:
    moment = to_exchange(value)
    return f"{moment.strftime('%H:%M')} {EXCHANGE_LABEL}" if moment else fallback


def date_short(value: Any, *, fallback: str = "undated") -> str:
    """'2026-10-07' in exchange time (a session date, not a UTC instant date)."""
    moment = to_exchange(value)
    return moment.strftime("%Y-%m-%d") if moment else fallback


def full(value: Any, *, fallback: str = "time unavailable") -> str:
    moment = to_exchange(value)
    if moment is None:
        return fallback
    return f"{moment.strftime('%Y-%m-%d %H:%M:%S')} {EXCHANGE_LABEL}"


def market_session_state(now: dt.datetime | None = None) -> dict[str, Any]:
    """Regular-session state in exchange time. Informational only."""
    moment = (now or dt.datetime.now(dt.timezone.utc))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    local = moment.astimezone(EXCHANGE_TZ)
    weekday = local.weekday()
    minutes = local.hour * 60 + local.minute
    if weekday >= 5:
        state = "CLOSED_WEEKEND"
    elif minutes < 9 * 60 + 30:
        state = "PRE_MARKET"
    elif minutes < 16 * 60:
        state = "REGULAR"
    elif minutes < 20 * 60:
        state = "AFTER_HOURS"
    else:
        state = "CLOSED"
    return {"state": state, "exchange_time": local.strftime("%H:%M:%S"),
            "label": EXCHANGE_LABEL, "is_regular": state == "REGULAR"}


def js_helpers() -> str:
    """Browser-side equivalents, so client-rendered times match the server's."""
    return """
// Times are rendered in EXCHANGE time (US/Eastern), never UTC. The browser's own
// zone is irrelevant: a trader reads market time.
const EXCHANGE_TZ='America/New_York';
function exTime(v,withSeconds){
  if(v==null||v==='')return '—';
  const d=new Date(v);
  if(isNaN(d.getTime()))return '—';
  return d.toLocaleTimeString('en-US',{timeZone:EXCHANGE_TZ,hour12:false,
    hour:'2-digit',minute:'2-digit'+(withSeconds?':2-digit':'2-digit'),
    ...(withSeconds?{second:'2-digit'}:{})});
}
function exStamp(v,label){
  if(v==null||v==='')return esc(label||'time unavailable');
  const t=exTime(v,true); if(t==='—')return esc(label||'time unavailable');
  return t+' ET';
}
function exDate(v){
  if(v==null||v==='')return 'undated';
  const d=new Date(v); if(isNaN(d.getTime()))return 'undated';
  return d.toLocaleDateString('en-CA',{timeZone:EXCHANGE_TZ});
}
function exSession(){
  const d=new Date();
  const p=new Intl.DateTimeFormat('en-US',{timeZone:EXCHANGE_TZ,weekday:'short',
    hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(d);
  const get=t=>(p.find(x=>x.type===t)||{}).value;
  const wd=get('weekday'), hh=Number(get('hour'))%24, mm=Number(get('minute'));
  if(wd==='Sat'||wd==='Sun')return 'CLOSED_WEEKEND';
  const mins=hh*60+mm;
  if(mins<570)return 'PRE_MARKET';
  if(mins<960)return 'REGULAR';
  if(mins<1200)return 'AFTER_HOURS';
  return 'CLOSED';
}
"""
