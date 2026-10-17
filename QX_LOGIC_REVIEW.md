# QX Trading Workspace — Complete Logic for Independent Review

**Version:** as built · **App:** http://127.0.0.1:8790 · **Prepared for:** external code/quant review

This document is self-contained. A reviewer should be able to verify every rule,
threshold and claim **without reading the codebase first**. Where something is
unverified or limited, it says so plainly rather than implying more.

---

## 0. How to review this

| What to check | Where the evidence is |
|---|---|
| Rule formulas | §3 (Momo/Trend), §4 (5 Phases), §5 (MASTER AUTO) |
| Thresholds & configurable parameters | §3–§5 tables, §6 |
| Breadth / denominator / weight coverage | §7 |
| Entry quality vs alignment separation | §8 |
| Safety invariants (no EXECUTABLE, no live order) | §9, §12 |
| Test evidence | §13 (every suite + counts) |
| Known limitations & unverified behaviour | §15 — **read this first** |

**Honest summary up front:** the three indicator studies were ported from
ThinkScript supplied by the user (one of them was already in the repo). They are
verified against hand-computed expectations and empirically-located fixtures, but
they have **not** been validated against TradingView/ThinkScript output
side-by-side, and no parameter here has been optimised or back-tested for
profitability. Treat every threshold as a *declared starting point*, not a proven
optimum.

---

## 1. Architecture

```
Schwab REST (read-only)          stockanalysis.com (holdings)
        |                                   |
        v                                   v
  qx/scanner/engine.py  <-----  qx/explorer/membership.py
  (bars + quotes, cache fallback)   (two universes, provenance)
        |
        v
  qx/scanner/studies.py  (EMA/RSI/MACD/ATR/VWAP-σ + factor scoring)
        |
        +--> qx/explorer/momo_trend.py     (Momo / Trend)
        +--> qx/explorer/market_phases.py  (James Boyd 1-5)
        +--> qx/explorer/master_auto.py    (bias/trigger/entry/exit/plan)
        |
        v
  qx/explorer/service.py   (explore one ETF -> classified members + breadth)
  qx/explorer/ideas.py     (aggregate candidate snapshot + views + ranking)
        |
        v
  qx/app/server.py  (HTTP routes)  ->  qx/app/ui.py (pages)
  qx/app/explorer_notes.py, qx/notes/engine.py (evidence-linked notes)
  qx/reporting/*  (read-only account history, FIFO P&L, reports)
```

**Separation of concerns — deliberate:**
- Deterministic services own all scoring, states, breadth and eligibility.
- Notes/explanations are **generated from stored evidence**, not from a model, so
  every statement is verifiable.
- Nothing in the explorer can set execution eligibility.

---

## 2. Data contracts

### 2.1 Bars
`{open, high, low, close, volume}` ascending, **completed bars only** by default.
Live Schwab first, cached CSV fallback, with the source always reported
(`schwab` | `cache` | `none`).

### 2.2 Two membership universes — never substituted

| ID | Source | Weights | Verified size/coverage |
|---|---|---|---|
| `ETF_REPORTED_TOP_HOLDINGS` | `stockanalysis.com/etf/{sym}/holdings/` | **Yes** (weight + shares) | **Top 25 only.** SMH 99.99% of weight, XLE 99.80% → representative. XLK 84.59% of 78 → **partial** |
| `CLASSIFIED_MEMBERS` | saved classified CSV via repo membership provenance | No | Returns `MEMBERSHIP_UNAVAILABLE` if absent — **never** falls back to holdings |

A request for one universe **cannot** silently return the other (asserted in tests).

### 2.3 Non-equity filtering
Rows matching `(DEC|MAR|JUN|SEP)\d{2}`, `FUTURES`, `CASH`, `CURRENCY`, `USD` are
dropped and counted. **This is not hypothetical:** XLE genuinely contains a futures
row (`IXPZ6 / XAE ENERGY DEC26 / -0.00%`).

### 2.4 Identity
Deduplication is by instrument identity, not ticker text. Share-class dots are
normalised (`BRK.B` → `BRK-B`), conflicting aliases are rejected, and **ADRs are
preserved** (TSM appears in SMH). A name held by several ETFs is counted **once**
and records the others in `also_in`.

---

## 3. TOPS-MultiTrend v4 — "Momo" and "Trend"

Ported verbatim from the user's ThinkScript. **Not present in the repo** (the 12
`.tos` files are SMC/CVD/VSCORE/ORB/RS studies).

```
MA10  = ExpAverage(close, 10)        # note: not used for Momo/Trend
EMA34High  = ExpAverage(high,  34)
EMA34Close = ExpAverage(close, 34)   # present in the study but NEVER USED
EMA34Low   = ExpAverage(low,   34)
EMA8 = ExpAverage(close, 8); EMA13 = ExpAverage(close, 13); EMA21 = ExpAverage(close, 21)

bullish  = (EMA8 > EMA13) and (EMA13 > EMA21)
bearish  = (EMA8 < EMA13) and (EMA13 < EMA21)
sideways = !bullish and !bearish

WaveState = IF bullish AND (EMA21 > EMA34High) THEN Bullish
            ELSE IF bearish AND (EMA21 < EMA34Low) THEN Bearish
            ELSE SW

Momo  label = bullish / bearish / sideways
Trend label = WaveState Bullish / Bearish / SW
```

### Three porting decisions that change the signal
1. **The 34-wave uses EMA of `high` and EMA of `low`**, not close. `EMA34Close` is
   dead code in the study. Simplifying to a close EMA would change every Trend
   label.
2. **`WaveState` is recursive in ThinkScript** but re-evaluated per bar from that
   bar's own EMAs, so it is stateless — no carry-over to reproduce.
3. **Warmup = 5 × longest period = 170 bars.** ThinkScript seeds `ExpAverage` on
   bar 1; the repo's `ema()` seeds on the first value. Before warmup the state is
   `None`, **never a guess**. This is a deliberate divergence from ThinkScript's
   first-bar seeding — a reviewer may prefer to match seeding exactly; see §15.

### The behavioural finding that shapes everything
**Momo and Trend genuinely disagree**, which is why the study exposes two labels.
Verified with an empirically located fixture (`scratch/find_divergence.py`):

```
flat 200 bars then +0.05/bar:
  EMA21 = 101.41   EMA34High = 102.16
  Momo = BULLISH   Trend = SIDEWAYS   -> NOT aligned

decisive ramp (+0.4/bar):
  EMA21 = 111.31   EMA34High = 110.31
  Momo = BULLISH   Trend = BULLISH    -> aligned
```

Therefore the explorer's default filter **requires both**, and momentum alone can
never confer alignment.

---

## 4. James Boyd 5 Market Phases

**This study was already in the repo** at
`.agents/skills/smc-rules-engine/resources/tos_james_boyd_market_phases.tos`; the
port uses the repo copy as authoritative.

```
MA10 = movingaverage(EXPONENTIAL, close, 10)
MA30 = movingaverage(SIMPLE,      close, 30)
hull = HullMovingAvg(close, 10)

phase1 = close < MA10 AND close < MA30     # downtrend
phase2 = close > MA10 AND close < MA30     # early reversal
phase3 = close > MA30 AND close > MA10     # strong uptrend
phase4 = phase3 AND (MA10 > MA30) AND (hull <= hull[1])   # pullback WARNING
phase5 = close < MA10 AND close > MA30     # support bounce

HMA(n) = WMA( 2*WMA(close, n/2) - WMA(close, n), sqrt(n) )   # n/2=5, sqrt(10)=3
```

### Three subtleties
1. **Phase 4 must be tested FIRST.** The study comments *"Test for P4 up front,
   because it is a subset of P3."* A Phase 4 bar also satisfies `phase3`, so
   numeric ordering would label distribution as a healthy trend. Implemented
   precedence: **P4 > P1 > P2 > P3 > P5**.
2. **Phase 3's documented pale-green never renders.** Both
   `AssignBackgroundColor` branches resolve to `Color.DARK_GREEN`. The port exposes
   `phase3_ma_crossed` separately rather than contradicting the study's actual
   behaviour.
3. **Strict inequalities leave a gap.** `close == MA10` satisfies neither
   `closeAbove10` nor `closeBelow10`, so the label chain falls through to blank.
   The port returns `phase=None, reason=INDETERMINATE` — it does not invent a phase.

**Warmup = 5 × 30 = 150 bars.**

---

## 5. QX MASTER AUTO FAST v5.2.4 — the entry/exit system

Ported from the user's ThinkScript. **Not in the repo.** This is a complete signal
system, so the port preserves its exact evaluation order.

### 5.1 VWave — movement-weighted mean (NOT an EMA, NOT a VWAP)

```
movement = Max(high - low, AbsValue(close - close[1]))
VWave(source, n) = Sum(source * movement, n) / Sum(movement, n)
                   ( falls back to `source` when movementSum == 0 )

waveHigh   = VWave(high,  34)     waveLow  = VWave(low,  34)
waveCenter = VWave(close, 34)
waveFast/Mid/Slow = VWave(close, 8 / 13 / 21)
```

Verified: equals the plain window mean under uniform movement; scales linearly
with source; **differs** from `EMA(close,34)` on a trend.

### 5.2 States

```
bullStack = fast > mid > slow          bearStack = fast < mid < slow
bullRegime = bullStack AND waveSlow > waveHigh      <-- strict, unusual
bearRegime = bearStack AND waveSlow < waveLow
bullBuild  = bullStack AND close > waveCenter
bearBuild  = bearStack AND close < waveCenter
```

`bullRegime` requires the **21-period close wave above the 34-period HIGH wave**.
`waveHigh` sits above and lags, so this is demanding — measured **114 of 184** warm
bars on a wavy uptrend satisfied it. **This is not a typo to "fix".**

### 5.3 RSI (Wilder) — including an apparent study bug reproduced verbatim

```
advPrice = Wilder(Max(close - close[1], 0), 14)
decPrice = Wilder(AbsValue(Min(close - close[1], 0)), 14)
rsi = 100 if decPrice == 0 else (0 if advPrice == 0 else 100 - 100/(1 + adv/dec))

rsiOverbought = rsi >= 70
rsiOversold   = rsi <= 30
rsiBullish    = rsi > 50 AND !rsiOverbought
rsiBearish    = rsi < 50 AND !rsiOverbought     # <-- guards OVERBOUGHT, not oversold
```

`rsiBearish` guarding `rsiOverbought` looks like a copy/paste error in the
original. It is **reproduced verbatim** (it only affects the RSI *label* colour,
not any gate). A reviewer may want this corrected upstream — flagged in §15.

### 5.4 Bias latch (CompoundValue — stateful, order-dependent)

```
superTrend: HL2 +/- mult*ATR(lookback), latch: close < superTrend[1] ? upper : lower,
            seeded from stLower.  ATR is a HULL moving average of TrueRange.
biasSlopeBars = 3, biasFlipConfirmBars = 2

bullEvidence = centerRising AND slowRising AND close > waveCenter AND (!useST OR stBull)
bullConfirmed = bullEvidence AND Sum(bullEvidence, 2) == 2

biasState = CompoundValue(1,
    if bullConfirmed then 1 else if bearConfirmed then -1 else biasState[1], 0)
```

Bias **latches** ±1 and **never returns to 0**.

### 5.5 Trigger, entry and exit

```
triggerLength: 3 (1m) / 5 (5m) / 5 (daily); buffer = 1 tick
localHigh = Highest(high[1], triggerLength)
callTriggerPrice = localHigh + TickSize * buffer

callReady  = bullRegime AND close > waveHigh AND vwapOK AND volumeOK
callActive = callReady AND bullCandle AND (breaksUp OR crossUp)
             where crossUp = close > waveHigh AND close[1] <= waveHigh[1]
callCandidate = callActive AND !callActive[1]      # RISING EDGES, never levels
callExitBase  = close < waveCenter OR (vwap filter AND intraday AND close < vwap)
                OR bearStack

tradeDirection = CompoundValue(1,
    if dir==0 and callCandidate then 1
    else if dir==0 and putCandidate then -1
    else if dir==1 and callExitBase then 0
    else if dir==-1 and putExitBase  then 0
    else dir, 0)
```

**Two independent arms** in `callActive` — a buffered break of the recent high OR
a fresh cross above `waveHigh`. Dropping the second arm loses cross-without-break
entries.

### 5.6 Trade plan (this is what feeds the order ticket)

```
atr = SMA(TrueRange, 14)
mult = atrStopMultiplier = 1.10
entry = close at signal
stop    = entry -/+ atr * 1.10
target1 = entry +/- atr * 1.10 * 1.00     -> exactly 1.0R
target2 = entry +/- atr * 1.10 * 2.00     -> exactly 2.0R
```

Verified exactly: `risk = atr*mult`, `T1 = risk*1.0`, `T2 = risk*2.0`, targets on
the correct side for direction.

### 5.7 RVOL — two different bar offsets (a real bug I introduced and fixed)

```
rvolLive      = volume        / Average(volume[1], n)   # chart's LAST bar only
rvolCompleted = volume[1]     / Average(volume[2], n)   # everywhere else
   => on bar i: volume[i] / mean(volume[i-n : i])
```

My first port used `avg[i-1]` and was **shifted by one bar** (reported 1.0 where
4.0 was correct). Also `is_last` must mean the **chart's** last bar, not the loop's
last iteration, because `forming=False` excludes the final bar.

**Autotimeframe RVOL thresholds:** 1m → 0.85 / 1.15; 5m → 0.95 / 1.25; else
0.90 / 1.20 (min / strong).

---

## 6. Configurable parameters (all explicit, none claimed optimal)

| Parameter | Default | Where |
|---|---|---|
| `wave_length` | 34 | MASTER AUTO |
| `fast/mid/slow_wave_length` | 8 / 13 / 21 | MASTER AUTO |
| `atr_length` | 14 | MASTER AUTO |
| `atr_stop_multiplier` | **1.10** | MASTER AUTO |
| `target1_r` / `target2_r` | **1.00 / 2.00** | MASTER AUTO |
| `trigger_length` | 3/5/5 by timeframe | MASTER AUTO |
| `trigger_buffer_ticks` | 1 | MASTER AUTO |
| `bias_slope_bars` | 3 | MASTER AUTO |
| `bias_flip_confirm_bars` | 2 | MASTER AUTO |
| `min/strong_relative_volume` | 0.90 / 1.20 | MASTER AUTO |
| `supertrend_atr_length` | 5 / 8 / 8 | MASTER AUTO |
| `supertrend_multiplier` | 1.25 / 1.75 / 1.75 | MASTER AUTO |
| `extended_atr_multiple` | **1.5** | **Explorer (mine)** |
| `near_trigger_atr` | **0.5** | **Explorer (mine)** |
| `min_history_bars` | **180** | **Explorer (mine)** |
| `WARMUP_MULTIPLE` | 5 × longest period | all ports (mine) |
| `SNAPSHOT_TTL_SECONDS` | 6 h | ideas |
| `HOLDINGS_TTL_SECONDS` | 12 h | membership |

Rows marked **mine** are not from any user study — they are declared cutoffs I
chose and they are **not validated**. A reviewer should treat them as the highest
priority for scrutiny.

---

## 7. Breadth — denominator and weight coverage are mandatory

```
eligible  = members with momentum and trend computed
covered   = eligible with history_ok  (>= min_history_bars)
missing   = eligible - covered
trend_up_pct = |trend == BULLISH| / covered
aligned_pct  = |momentum == BULLISH AND trend == BULLISH| / covered

holdings_weighted_aligned_pct = sum(weight of aligned) / sum(weight of eligible)
weight_covered_pct            = sum(weight of eligible) * 100
```

**Rules enforced:**
- Breadth is computed **BEFORE display filters** and reports its own denominator.
- `PARTIAL UNIVERSE` is raised whenever `weight_covered_pct < 95`.
- Equal-weight and holdings-weighted are reported **together** — a large gap means
  the move is concentrated in big holdings, which is exactly the "distinguish broad
  participation from an ETF rise dominated by a few large holdings" requirement.

**Caution for the reviewer:** because the source serves only the **top 25**, a
broad fund's breadth is mega-cap-biased. XLK is the worked example (25 of 78,
84.59%).

---

## 8. Entry quality — deliberately separate from alignment

`classify_entry()` returns one of:

```
TRIGGER_CONFIRMED    a live plan exists (MASTER AUTO direction latched)
BREAKOUT_WATCH       regime + breakout + volume, awaiting the entry candle
PULLBACK_CANDIDATE   building inside the structure
EXTENDED_WAIT        beyond the chase limit
BLOCKED_RESISTANCE   (reserved; requires a resistance model not yet wired)
BLOCKED_DATA         insufficient history
NOT_ALIGNED          no qualifying structure
```

Mapping to Trade Ideas buckets: `TRIGGER_CONFIRMED → ready_now`,
`BREAKOUT_WATCH → near_trigger`, `PULLBACK_CANDIDATE → pullback_watch`.

**`EXECUTABLE` is not in this vocabulary.** The strongest state alignment can reach
is `TRIGGER_CONFIRMED`.

---

## 9. Safety invariants (asserted by tests, not by convention)

1. **Alignment can never produce `EXECUTABLE`.** Every candidate's `entry_state` is
   checked; `EXECUTABLE` appears nowhere. Execution eligibility remains owned by the
   repo's `OrderRouter.validate_execution_eligibility`, which requires
   `publication_state == VERIFIED and executable is True` — a layer this code
   **cannot set**. In practice it reports **BLOCKED** (`RESEARCH_ONLY`).
2. **No live order.** The Trade Workspace stages **application-level simulated**
   orders only; the live button is created `disabled`. Duplicate submissions are
   refused by a ticket-hash intent ledger.
3. **Universal label.** Every page carries `LIVE EXECUTION DISABLED · SIMULATED ONLY`.
4. **Secrets.** The client secret value and raw tokens never appear in a payload or
   the DOM (asserted). Client ID is masked. OAuth state is reported, not tokens.
5. **Simulated orders are labelled** `mode: SIMULATED, app_level: true` and are
   never presented as the repo's EX-gate approval.
6. **No fabricated data.** Missing holdings → `MEMBERSHIP_UNAVAILABLE`; missing
   history → `UNKNOWN`; no holdings date → reported as unknown rather than re-dated.

---

## 10. Notes — deterministic, evidence-citing, self-invalidating

Two note engines, **no model call**:

- `qx/notes/engine.py` — 7 sections (why it qualifies · market/sector alignment ·
  entry & invalidation · targets & management · conflicting evidence & event risks ·
  what changed · post-trade review). 6 commands. Staleness is a **pure function of
  an evidence digest** over exactly the cited keys; unchanged evidence stays FRESH,
  moved evidence flips to STALE with before/after digests.
- `qx/app/explorer_notes.py` — per-stock: why aligned · leads parent/market ·
  participation supports it · entry attractive or extended · conflicting evidence ·
  what must happen next.

Every note carries timestamps, rule versions, missing inputs, and an explicit
`cannot:` list (alter scores / change a ticket / submit an order / claim a fill).

---

## 11. Trade Ideas — one candidate set, several views

**Measured constraint:** one sector costs ~19–25 s because bars are fetched per
member, while all three studies together are **~0.06 s per symbol**. Live
aggregation across 23 ETFs would take minutes, so ideas are built into a
**snapshot** by a background job and the page reads it, always showing age and
flagging staleness past 6 h.

Full-universe result: **23 ETFs, 453 unique candidates, 0 errors.**

| View | Meaning | Count (last full run) |
|---|---|---|
| Ready now | live plan latched | 191 |
| Near trigger | structure present, no entry candle | 56 |
| Pullback watch | building, awaiting pullback | 118 |
| Newly aligned | **discovery candidates, NOT trades** | 4 |
| Bearish | momentum down + trend down | 174 |

Views are **filters over the same records** — asserted: all five report the same
`row_count`. Five sorts (entry readiness / newly aligned / parent-relative /
market-relative / distance to trigger) **never change membership** — asserted.
`NOTHING_QUALIFIES` is a first-class visible state; no quota is manufactured.
"Why ranked here?" gives position, bucket, RS figures and alignment age, and
disclaims a universal score.

---

## 12. Systematic scanner factor model (the older layer, for completeness)

```
QX Score = 0.25*SMC + 0.20*Phases + 0.20*CVD_Absorption
         + 0.15*VScore + 0.10*RS_Rank + 0.10*OptionsFlow
score >= 70 -> LONG / BUY CALL ; score <= 30 -> SHORT / BUY PUT ; else WAIT
```

SMC = 21-day high/low breakout + higher-highs + EMA20>EMA50.
Phases = EMA20/EMA50 slope + price position.
CVD = cumulative signed-volume z-score + wick/body absorption.
VScore = (price − anchored VWAP)/σ mapped to 0–100.
RS_Rank = 10/60/252-day excess return vs benchmark.
OptionsFlow = **realised-volatility proxy, not observed order flow** — weakest input,
stated as such in the notes.

Implemented on the MASTER AUTO / Boyd / Momo layers now; still used by the Discover
scanner results table.

---

## 13. Test evidence

All suites run headless against the live app and live Schwab data.

| Suite | File | Result |
|---|---|---|
| TOPS-MultiTrend rules | `scratch/audit_momo_trend.py` | **29 / 29** |
| James Boyd 5 Phases | `scratch/audit_market_phases.py` | **31 / 31** |
| MASTER AUTO rules | `scratch/audit_master_auto.py` | **37 / 37** |
| Explorer service (live) | `scratch/audit_explorer.py` | **39 / 39** |
| Explorer HTTP | `scratch/audit_explorer_http.py` | **32 / 32** |
| Ideas service | `scratch/audit_ideas.py` | **39 / 39** |
| Ideas HTTP | `scratch/audit_ideas_http.py` | **33 / 33** |
| Notes | `scratch/audit_notes.py` + `_http` | **18 / 18** |
| Browser: Discover explorer | `web/tests/qx-explorer.cjs` | **25 / 25** |
| Browser: Trade Ideas | `web/tests/qx-trade-ideas.cjs` | **31 / 31** |
| Browser: full app | `web/tests/qx-workspace-integration.cjs` | **61 / 61** |
| Browser: reports drill-down | `web/tests/qx-reports-drilldown.cjs` | **19 / 19** |
| Browser: context + settings | `web/tests/qx-context-settings.cjs` | **20 / 20** |

Plus `scratch/audit_all_scripts.py`, which runs `node --check` over **every**
embedded page script — added after four escaping bugs had silently blanked a page.

**Specific cases a reviewer should look at** (all covered):
UP/UP, UP/SIDEWAYS (divergence), DOWN/SIDEWAYS, DOWN/DOWN, flat → INDETERMINATE,
short series → no state, forming vs completed bar, phase-4-beats-phase-3, Hull
reference parity, RVOL both offsets, no two consecutive signal bars, no duplicates
by identity, breadth reconciles to the covered universe, no EXECUTABLE.

---

## 14. Real bugs found and fixed during this work

Reporting these because they are the evidence that verification was real:

1. **RVOL off-by-one** (MASTER AUTO) — read 1.0 where 4.0 was correct.
2. **`is_last`** meant loop-end, not chart-end → live-RVOL branch unreachable.
3. **ATR slice/index mismatch** on the Context page → 191.5 on a $777 instrument; now 7.29.
4. **`/NQ` basis vs SPX cash** → +303%; now +0.93% vs `$NDX`.
5. **Missing `pct()` helper** → whole gamma panel blank.
6. **Four inline-handler escaping bugs** → Reports page stuck on "Loading…".
7. **Signed-quantity divide** in FIFO P&L → flipped every closing leg (−$18.2M nonsense).
8. **`hashValue` required** for Schwab transactions/orders (plain account number → HTTP 400).
9. **Multi-account**: the token exposes two accounts; the legacy
   `SchwabReadOnlyAccountSnapshotProvider` returns `None` when >1 account is
   readable, so the Portfolio page is silently empty. **Not fixed** — see §15.
10. **Module shadowing**: `qx.explorer.__init__` re-exported a function named
    `ideas`, shadowing the `qx.explorer.ideas` module and 500-ing `/api/ideas/status`.

---

## 15. Known limitations and unverified behaviour — REVIEW THESE

1. **No ThinkScript side-by-side validation.** The ports match hand-computed
   expectations and deliberate fixtures, but I have **not** compared them
   bar-by-bar against TradingView output. Highest-value review action.
2. **EMA seeding differs from ThinkScript** (documented in §3.3). Early values
   differ; warmup masks most of it.
3. **`extended_atr_multiple=1.5`, `near_trigger_atr=0.5`, `min_history_bars=180`
   are mine and unvalidated.** Not from any study.
4. **`rsiBearish` guards overbought** — reproduced from the study, likely an
   upstream typo (§5.3).
5. **Holdings are top-25 only.** SMH/XLE representative, XLK (84.59% of 78) is not.
   Breadth on broad funds is mega-cap-biased.
6. **`CLASSIFIED_MEMBERS` has no populated data** — it correctly returns
   `MEMBERSHIP_UNAVAILABLE`; no classified constituents are wired yet.
7. **`BLOCKED_RESISTANCE` is reserved but unreachable** — no resistance model wired.
8. **Options evaluation is always `UNDERLYING_ONLY`.** No chain-driven instrument
   selection; SPX 1–2DTE profiles are not separated from swing.
9. **Multi-account Portfolio bug unfixed** (§14.9).
10. **No alerts implemented** despite the brief listing them (transitions exist:
    `newly_aligned`, `lost_alignment`, `entered_warning`, `phase_changed`).
11. **No chart grid** — deliberately deferred; table mode only.
12. **Settlement provenance is `HEURISTIC_DTE / HEURISTIC`** on GEX — declared, not
    verified.
13. **Order placement, preview and any Schwab paper/sandbox environment remain
    UNVERIFIED.** Web search was unavailable (HTTP 402) and Schwab's developer docs
    return HTTP 403 from this machine. Live order payloads have therefore never been
    exercised.
14. **No live trade has ever been placed**, by design.
15. **Single-process HTTP server** (stdlib `ThreadingHTTPServer`), loopback-bound,
    **no authentication**. It binds 127.0.0.1 only, but it is not hardened.

---

## 16. Questions I would put to a reviewer

1. Should EMA seeding match ThinkScript exactly, or is warmup-masked divergence
   acceptable?
2. Is `bullRegime`'s `waveSlow > waveHigh` intended as written (it makes Regime
   rare), or should it compare against `waveCenter`?
3. Should `rsiBearish` be corrected to `!rsiOversoldState`?
4. Are the explorer cutoffs (1.5 ATR extended, 0.5 ATR near-trigger, 180-bar
   minimum) defensible, and what would you set?
5. Is a 25-holding universe acceptable for breadth, or must a full constituent
   source be found before the breadth numbers are published?
6. Should `ready_now` be renamed, given it means "a study plan is live" rather than
   "ready to send an order"?
7. Ranking has no universal score. Is separating by concern the right call, or do
   you want one blended rank?
