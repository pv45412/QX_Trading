# Backtest results — what the QX rules actually do

**Run date:** 2026-09-10 · **Data:** 2 years of daily bars (2024-09-10 → 2026-09-10)
**Method:** `src/qx/backtesting/` — next-bar-open execution, 2 bps round-trip cost, causality verified.

---

## 1. Headline

| | Study exit (as shipped) | Stop enforced | Buy & hold |
|---|---|---|---|
| Trades | 6,044 | 6,044 | — |
| Mean R per trade | **−0.1385** | **−0.1650** | — |
| Median R | −0.8875 | — | — |
| Win rate | 34.6% | — | — |
| Profit factor | **0.884** | — | — |
| Total | **−837.0 R** | — | — |
| Mean return | — | — | **+40.8%** |
| Median return | — | — | +18.1% |
| % positive | — | — | 64.6% |

Over 1,196 clean symbols and 2 years, the shipped rule set loses money on every trade on
average. Buy-and-hold over the same window and the same symbols returns +40.8% mean.
**The rules did not beat holding.**

Causality was verified before any of this was trusted: 4/4 sampled decision points produced
identical decisions when future bars were hidden. The result is not a lookahead artifact.

---

## 2. What a trade actually resolves to

The UI displays **R:R 2.0** for every row. The realized distribution:

| Statistic | Value |
|---|---|
| mean R | −0.1385 |
| median R | −0.8875 |
| p10 | −2.827 |
| p90 | +4.953 |
| best | +16.97 |
| worst | −7.935 |

Median outcome is **−0.89R**. The displayed 2.0 is `cfg target2_r = 2.00` — a constant that no
condition reads. It is not a measured property of the strategy.

---

## 3. The stop question (F23)

The app shows an ATR-derived reference stop at roughly 1R. Adverse excursion measured:

| Statistic | Value |
|---|---|
| median MAE | −1.8 R |
| p05 MAE | −3.94 R |
| worst MAE | −8.17 R |
| trades beyond −1R | **71.1%** |
| trades beyond −2R | **40.2%** |

71% of trades trade through the displayed stop level before resolving. Enforcing it would
have stopped out seven trades in ten. The `REFERENCE_ONLY` labelling applied to that level
in the UI is therefore correct and should stay.

Policy comparison: study exit −0.138 vs stop enforced −0.165 → `NO_MATERIAL_DIFFERENCE`.
Neither is profitable; the stop mainly truncates the left tail (p05 MAE −3.94 → −1.45).

---

## 4. Parameter sweep — which settings actually matter

Universe 1,196 symbols. Every row below changed one setting from the shipped default:

| Setting | Trades | Mean R | PF | Total R |
|---|---|---|---|---|
| **BASE (as shipped)** | 6,044 | −0.1385 | 0.884 | −837.0 |
| **wave_length 34 → 55** | 5,060 | **−0.0385** | **0.967** | **−194.6** |
| RVOL gate → 1.20 | 4,706 | −0.0995 | 0.916 | −468.4 |
| RVOL gate → 1.50 | 3,454 | −0.1005 | 0.917 | −347.0 |
| RVOL gate → 2.00 | 2,071 | −0.0999 | 0.916 | −206.8 |
| trigger length 5 → 10 | 5,861 | −0.1364 | 0.886 | −799.6 |
| trigger length 5 → 20 | 5,770 | −0.1418 | 0.882 | −818.2 |
| volume filter OFF | 6,969 | −0.1484 | 0.872 | −1,034.4 |
| supertrend bias OFF | 6,044 | −0.1385 | 0.884 | −837.0 |
| bias confirm 2 → 4 | 6,044 | −0.1385 | 0.884 | −837.0 |
| RSI band 70/30 → 80/20 | 6,044 | −0.1385 | 0.884 | −837.0 |
| ATR stop ×1.1 → ×3.0 | 6,044 | −0.1385 | 0.884 | −837.0 |
| waves 8/21 → 13/34 | **0** | — | — | — |

**Every row remains negative.** The best configuration found (`wave_length 55`) still loses
money, just more slowly. No setting tested produces a positive expectancy.

### 4a. Two settings are dead gates

`sweep validity` — `rsi_overbought 70→80` and `use_vwap_filter OFF` changed **0 bars** across
40 symbols. They are declared in `DEFAULTS` but no condition reads them. An operator toggling
them sees no change and no error.

### 4b. Four settings move the display but not the entries

Counting bars where the **entry** fields change (`trade_direction`, `call_ready`, `put_ready`,
`call_candidate`, `put_candidate`) across 40 symbols:

| Setting | Total bars changed | Entry bars changed |
|---|---|---|
| supertrend bias OFF | 2,739 | **0** |
| ATR stop ×3 | 3,973 | **0** |
| bias confirm 2→4 | 1,299 | **0** |
| RSI 80/20 | 0 | 0 |

These settings write `bias_state` and `active_stop` — both display fields — while leaving
every entry decision identical. This is why the sweep returned byte-identical trade counts.
**The same defect class as the stop and the target: a control that appears to change the
strategy but is wired only to the readout.**

### 4c. A combination that produces no trades at all

`fast_wave 8→13` with `slow_wave 21→34` yields **0 trades** across 1,196 symbols. The two
wave lengths are presumably expected to bracket each other; at 13/34 no entry condition can
ever be satisfied. Silent total failure, no error raised.

---

## 5. Study ablation — the filters look like a large edge

A 400-symbol sample (2,015 base trades). Each row is a subset of the base trades:

| Subset | Trades | Mean R | Win rate | PF | Final R |
|---|---|---|---|---|---|
| ALL (base) | 2,015 | −0.0635 | 35.4% | 0.947 | −127.9 |
| Momo + Trend aligned | 684 | **+0.2847** | 41.1% | **1.248** | +194.7 |
| **Boyd phase 3** | 980 | **+0.4249** | 41.1% | **1.386** | **+416.4** |
| Boyd phase 4 (pullback) | 18 | +1.7533 | 50.0% | 3.372 | +31.6 |
| Aligned AND phase 3 | 659 | +0.3077 | 41.6% | 1.268 | +202.8 |
| RS vs market > 0 | **0** | — | — | — | — |
| Aligned AND RS > 0 | **0** | — | — | — | — |

Taken at face value this is the most exciting table in the whole project: filtering to Boyd
phase 3 flips a −0.06R book into a +0.42R book with a 1.39 profit factor. **It does not
survive the control in section 6.**

Two buckets return zero trades. The relative-strength field (`RS vs market`) matches nothing —
the same dead-field defect class as section 4a. Either the field is never populated or the
simulator cannot index it. **No conclusion can be drawn about relative strength.**

---

## 6. Random-entry control — the decisive test

The window 2024-09 → 2026-09 is a bull market; buy-and-hold returned +40.8% mean. A filter that
selects "this stock is in a confirmed uptrend" will look brilliant in a bull market **even if the
entry moment carries no information at all** — it is just long exposure. So the filters above
prove nothing on their own.

The control: for each real trade, take the **same symbol, same direction, same holding period**,
and choose the entry bar at random. Only the entry *moment* differs. 20 draws per real trade,
seed 20260101.

| Slice | n (real) | REAL mean R | RANDOM mean R | **Edge** | σ |
|---|---|---|---|---|---|
| ALL base trades | 2,002 | −0.0843 | +0.3279 | **−0.4122** | −5.07 |
| LONG only | 1,068 | +0.4058 | +0.4130 | **−0.0072** | −0.06 |
| SHORT only | 934 | −0.6447 | −0.0356 | **−0.6091** | −6.36 |
| Boyd phase 3 | 980 | +0.4035 | +0.6734 | **−0.2699** | −2.12 |
| Boyd phase 3 — LONG only | 968 | +0.4215 | +0.6412 | **−0.2197** | −1.71 |

**No slice beats random entry timing. Every edge is negative.**

- **LONG only: −0.0072R (−0.06σ).** The long book is statistically indistinguishable from
  entering long at a random moment. The +0.41R per long trade is the market's drift, not the
  entry rule. The entire apparent edge of the long side is **beta**.
- **Boyd phase 3: −0.27R.** The best-looking filter in section 5 is *worse* than random timing in
  the same names. Its +0.42R was inherited from the long side, which the control shows carries no
  timing information.
- **SHORT only: −0.61R at −6.4σ.** The short signal is not merely useless, it is **actively
  anti-predictive**: shorting at a QX short signal did materially worse than shorting the same
  name at a random moment. This is the strongest single result in the backtest.

### A discarded control, for the record

A first control run used a **long-only** return formula and reported a *positive* +0.11R edge for
Boyd phase 3. That run was wrong: with no direction branch it computed the long return for short
trades, inverting every short's sign. Since shorts are the losers, inverting them manufactured a
fake edge. The direction-aware run above supersedes it. `scratch/backtest_control.json` holds the
invalid long-only result; `scratch/backtest_control_directional.json` holds the valid one.

### What this means, stated plainly

The layered studies — Momo, Trend, Boyd phase, and the rest — are **not adding entry timing
information** on this sample. They are a disciplined, repeatable way to be **long in an uptrend**,
which is exactly what a bull market rewards. The filters do change *what gets traded* (section 5
shows the subsets differ sharply); they do not change *whether the timing is good*.

---

## 7. Universe construction

| | |
|---|---|
| Cached symbols scanned | 1,544 |
| Entered simulation | **1,196** |
| Excluded — missing dates (point-in-time unprovable) | 243 |
| Excluded — insufficient history (<176 bars) | 41 |
| Excluded — no cached file | 3 |
| Excluded — suspected unadjusted split | 61 |

Split detection threshold 45% single-bar move. Worst cases: TRVN +24,900%, TTOO +3,733%,
SRNE +1,775%, MRNA +177%. These are unadjusted corporate actions; they are **detected and
excluded, not corrected**.

---

## 8. Limitations — read before acting on any of this

1. **Two years is one regime.** 2024-09 → 2026-09 is a single bull period. Buy-and-hold's
   +40.8% mean is partly that regime, not skill. The strategy's loss is not regime-explained.
2. **Survivorship.** Only symbols with cached data today. Delisted losers are absent.
3. **Daily bars only.** No intraday path. A stop hit intraday but closed above is invisible;
   this systematically *understates* stop-outs and *overstates* study-exit outcomes.
4. **No slippage beyond 2 bps.** Thin names would be worse.
5. **Excluded splits bias upward.** Removing 61 violent movers removes some large winners.
6. **This answers "does it have an edge", not "how much money".** The answer to the first is
   no, at the tested settings. That is the finding, and it is robust to the caveats above —
   all five biases push *in favour* of the strategy, and it still loses.

---

## 9. What follows from this

1. **The layered studies have not demonstrated entry-timing edge.** Section 6 is the finding:
   long ≈ random long (−0.0072R), short *worse* than random short (−0.61R at −6.4σ). Every filter
   subset that looked profitable in section 5 was long exposure in a bull market. Treat the study
   stack as a *screening* tool — "here is a liquid name in a confirmed uptrend" — not as a timing
   signal. It does not currently earn its keep as the latter.
2. **Do not enable execution.** Governance already blocks broker writes. This is independent
   confirmation that the block is correct, not merely cautious.
3. **The short side should be switched off before anything else is tuned.** At −6.4σ against a
   random-entry control it is not underperforming, it is inverted. A +0.41R long book and a
   −0.64R short book in one system means the short rules are fighting the long rules.
4. **`wave_length 34 → 55` is the one lead worth chasing** — −0.0385R is near breakeven and
   materially better than base. Worth understanding *why* before tuning it further. Note this
   needs its own random-entry control; a near-zero mean R in a bull market is not evidence of skill.
5. **Fix or remove the dead and display-only controls.** `rsi_overbought`/`rsi_oversold`,
   `use_vwap_filter`, `use_supertrend_bias`, `bias_flip_confirm_bars`, `atr_stop_multiplier`
   either do nothing or change only the readout. An operator cannot tell which. The ablation's
   `RS vs market` buckets returning 0 trades is the same defect.
6. **The `waves 13/34` zero-trade case needs a guard** so an impossible configuration fails
   loudly instead of silently trading nothing.
7. **R:R 2.0 and the 1R stop should be removed from the UI as claims.** Backed by measurement,
   the honest display is the realized distribution above.

---

*Artifacts:* `scratch/backtest_full.json`, `scratch/backtest_sweep.json`,
`scratch/backtest_ablation.json`, `scratch/backtest_control_directional.json`,
`scratch/run_backtest_full.py`, `scratch/run_backtest_ablation.py`,
`scratch/run_backtest_control_dir.py`.
