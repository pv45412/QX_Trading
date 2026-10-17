"""Scratch: is the data realtime? Evidence, not assumption.

Checks, in order:
  1. what time is it, and is the regular session open?
  2. quote age from the quote's OWN timestamp (not retrieval time)
  3. the provider's own `realtime` flag
  4. whether option chains are delayed / truncated
  5. whether bars are EOD or intraday, and how old the latest bar is
"""
import datetime as dt
import os
import sys
import time

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.app import timefmt as T  # noqa: E402
from qx.scanner.engine import MarketData  # noqa: E402

now_utc = dt.datetime.now(dt.timezone.utc)
session = T.market_session_state(now_utc)
print("=== 1. clock and session ===")
print(f"  now            : {T.stamp(now_utc)}  ({now_utc.isoformat(timespec='seconds')})")
print(f"  session state  : {session['state']}  (is_regular={session['is_regular']})")
print()

market = MarketData()

print("=== 2/3. quotes: age from the quote's own timestamp ===")
print(f"  {'symbol':<8}{'last':>12}  {'age_s':>8}  {'realtime':>9}  observed_at")
for symbol in ("SPY", "QQQ", "AAPL", "NVDA", "IWM"):
    quote, source = market.quote(symbol)
    if not quote:
        print(f"  {symbol:<8}{'(none)':>12}  {'-':>8}  {'-':>9}  source={source}")
        continue
    stamp = quote.get("timestamp")
    age = market.quote_age_seconds(symbol)
    age_text = f"{age:.1f}" if isinstance(age, (int, float)) else "unknown"
    print(f"  {symbol:<8}{quote.get('last', 0):>12,.2f}  {age_text:>8}  "
          f"{str(quote.get('realtime')):>9}  {str(stamp)[:19]}")
    time.sleep(0.2)  # let the clock move so successive ages are comparable

print()
print("=== 3b. freshness classification (repo FreshnessChecker) ===")
for symbol in ("SPY", "NVDA"):
    f = market.freshness(symbol)
    print(f"  {symbol:<6} status={f['status']:<14} age={f['age_seconds']}s  "
          f"max={f.get('max_threshold_seconds')}s")
    print(f"         {f['reason']}")

print()
print("=== 4. option chains: delayed? truncated? ===")
from qx.app import context as C  # noqa: E402

for symbol in ("SPY", "$SPX"):
    try:
        g = C.gamma(symbol, max_expiries=2)
        chain = g.get("chain") or {}
        if g.get("error"):
            print(f"  {symbol:<6} error: {g['error'][:64]}")
        else:
            print(f"  {symbol:<6} is_delayed={chain.get('is_delayed')} "
                  f"is_truncated={chain.get('is_truncated')} "
                  f"contracts={chain.get('contracts')} expiries={chain.get('expiries')}")
    except Exception as exc:  # noqa: BLE001
        print(f"  {symbol:<6} EXC {type(exc).__name__}: {str(exc)[:60]}")

print()
print("=== 5. bars: daily vs intraday, and how old is the latest bar ===")
for interval in ("1d", "15m"):
    bars, source = market.bars("SPY", interval=interval)
    if not bars:
        print(f"  {interval:<5} no bars (source={source})")
        continue
    last = bars[-1]
    bar_date = last.get("date")
    age_days = None
    if bar_date:
        try:
            observed = dt.datetime.fromisoformat(bar_date)
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=dt.timezone.utc)
            age_days = (now_utc - observed).total_seconds() / 86400
        except ValueError:
            pass
    print(f"  {interval:<5} bars={len(bars):<5} source={source:<7} "
          f"last_bar={str(bar_date)[:19]} completed={last.get('bar_completed')} "
          f"age={f'{age_days:.2f}d' if age_days is not None else 'unknown'}")
