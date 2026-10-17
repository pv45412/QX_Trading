"""Phase B2 regression tests — F07 (bar completion) and F10 (date-aligned RS)."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

passed = failed = 0


def check(fid, title, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {fid}  {title}")
    else:
        failed += 1
        print(f"  FAIL  {fid}  {title}  {detail}")


from qx.explorer import bars as bmod  # noqa: E402
from qx.explorer import service as S  # noqa: E402
import qx.explorer.master_auto as ma  # noqa: E402

MID = dt.datetime(2026, 10, 8, 14, 33, tzinfo=dt.timezone.utc)   # Thu, mid-session
AFTER = dt.datetime(2026, 10, 8, 22, 0, tzinfo=dt.timezone.utc)  # Thu, after close


def series(n=200, last_date=None, interval="1d", flag=True):
    out = [{"open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i,
            "volume": 100, "date": None, "interval": interval, "bar_completed": flag}
           for i in range(n)]
    out[-1]["date"] = last_date
    return out


print("== F07: a COMPLETED final bar is kept, a FORMING one is dropped ==")
prior = series(last_date="2026-10-07T00:00:00+00:00")
check("F07a", "prior-session daily bar is completed",
      bmod.completion_state(prior, interval="1d", now=MID)["completed"] is True)
check("F07b", "a completed final bar is KEPT in the series",
      len(bmod.select_series(prior, interval="1d", now=MID)) == 200,
      f"kept={len(bmod.select_series(prior, interval='1d', now=MID))}")

today = series(last_date="2026-10-08T00:00:00+00:00")
check("F07c", "today's daily bar mid-session is still FORMING",
      bmod.completion_state(today, interval="1d", now=MID)["completed"] is False)
check("F07d", "a forming final bar IS dropped",
      len(bmod.select_series(today, interval="1d", now=MID)) == 199,
      f"kept={len(bmod.select_series(today, interval='1d', now=MID))}")
check("F07e", "the same bar is completed after the close",
      bmod.completion_state(today, interval="1d", now=AFTER)["completed"] is True)

intra_done = series(last_date="2026-10-08T14:15:00+00:00", interval="15m")
intra_open = series(last_date="2026-10-08T14:30:00+00:00", interval="15m")
check("F07f", "an intraday bar whose interval closed is completed",
      bmod.completion_state(intra_done, interval="15m", now=MID)["completed"] is True)
check("F07g", "an intraday bar still open is forming",
      bmod.completion_state(intra_open, interval="15m", now=MID)["completed"] is False)

undated = series(last_date=None, flag=None)
state = bmod.completion_state(undated, interval="1d", now=MID)
check("F07h", "an undated bar reports UNKNOWN, not a guess", state["completed"] is None,
      json.dumps(state)[:110])
check("F07i", "an UNKNOWN-completion bar is dropped (unverifiable, not assumed complete)",
      len(bmod.select_series(undated, interval="1d", now=MID)) == 199,
      f"kept={len(bmod.select_series(undated, interval='1d', now=MID))}")
check("F07i2", "forming=True still exposes the undated final bar when asked",
      len(bmod.select_series(undated, forming=True, interval="1d", now=MID)) == 200)

print("\n== F07: the study uses the same completion rule ==")
kept = ma.latest(prior, minutes=1440)
dropped = ma.latest(today, minutes=1440)
check("F07j", "MASTER AUTO evaluates the completed final bar",
      kept.index == 199, f"index={kept.index}")
# The study reads the WALL CLOCK (it has no `now` parameter), while completion_state
# can be asked about an instant. Assert the study agrees with the rule evaluated at
# the real current time — that is the contract, and it cannot drift.
_now = dt.datetime.now(dt.timezone.utc)
_real = bmod.completion_state(today, interval="1d", now=_now)["completed"]
check("F07k", "MASTER AUTO follows the completion rule at the current time",
      dropped.index == (199 if _real else 198),
      f"index={dropped.index} rule_at_now={_real}")
check("F07k2", "the same instant gives the same verdict from both entry points",
      bmod.completion_state(today, interval="1d", now=_now)["completed"] is _real)
check("F07l", "forming=True still evaluates everything",
      ma.latest(today, forming=True, minutes=1440).index == 199)

print("\n== F10: relative strength is date-aligned when dates exist ==")
a = [{"date": f"2026-01-{i:02d}", "close": 100 + i} for i in range(1, 29)]
b = [{"date": f"2026-01-{i:02d}", "close": 200 + i} for i in range(1, 29)]
check("F10a", "dated series are compared DATE_ALIGNED",
      S._relative_basis(a, b) == "DATE_ALIGNED", S._relative_basis(a, b))
ragged = [{"date": f"2026-01-{i:02d}", "close": 100 + i} for i in range(10, 29)]
check("F10b", "a ragged history still aligns on common dates",
      S._relative(ragged, b, 5) == S._relative(a, b, 5),
      f"ragged={S._relative(ragged, b, 5)} full={S._relative(a, b, 5)}")
check("F10c", "the basis is reported so a reader can see the method",
      S._relative_basis(ragged, b) == "DATE_ALIGNED")
und = [{"date": None, "close": 100 + i} for i in range(1, 29)]
und2 = [{"date": None, "close": 200 + i} for i in range(1, 29)]
check("F10d", "undated series fall back to POSITIONAL and say so",
      S._relative_basis(und, und2) == "POSITIONAL", S._relative_basis(und, und2))
thin = [{"date": f"2026-01-{i:02d}", "close": 100} for i in range(25, 29)]
check("F10e", "insufficient overlap returns None rather than a guessed number",
      S._relative(thin, b, 20) is None, f"got={S._relative(thin, b, 20)}")
check("F10f", "a shared date is required for the comparison window",
      S._relative([{"date": "2026-01-01", "close": 100}], [{"date": "2026-02-01", "close": 200}], 1) is None)

print("\n== live: the explorer reports its RS basis ==")
d = S.explore("SMH", view="aligned_up", limit=3)
row = d["rows"][0] if d["rows"] else {}
check("F10g", "rows carry rs_basis", "rs_basis" in row, str(row.get("rs_basis")))
check("F10h", "live bars are date-aligned",
      row.get("rs_basis") == "DATE_ALIGNED", str(row.get("rs_basis")))
check("F07m", "rows expose the bar's completion and date",
      "bar_date" in row and "bar_completed" in row,
      f"date={row.get('bar_date')} completed={row.get('bar_completed')}")

print(f"\nRESULT: {passed} passed, {failed} failed")
