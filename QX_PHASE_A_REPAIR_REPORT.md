# QX Phase A — Repair Report

Response to **QX_DEEP_CODE_REVIEW_DSH.md**. Scope: the reviewer's Phase A correctness
blockers (F01, F02, F03, F04, F05, F15). **Live execution remains disabled.**

---

## 1. Verification of the review — 16/16 reproduced

Before changing anything I reproduced every finding I checked against the current code
(`scratch/verify_review_findings.py`). **All 16 reproduced exactly as described.** I did
not dispute any finding, and I corrected my own earlier claim that `EXECUTABLE` "appears
nowhere" — that was true of the explorer path only (F04).

## 2. Failing-first tests

`scratch/test_phase_a.py` encodes the **correct** behaviour using the reviewer's own
fixtures. Baseline run on the unmodified code:

```
F02a-F02d  FAIL   F01a,F01c FAIL   F03a,F03b FAIL
F04a,F04b  FAIL   F05a,F05b FAIL   F15a FAIL
= 14 failures, 6 passes
```

After the fixes: **20 passed, 0 failed.**

---

## 3. What changed, with before/after evidence

### F01 — a latched historical trade is no longer promoted to readiness
Split four states that were conflated: `STUDY_SIGNAL` (the study's own latched opinion,
preserved for research parity), `ENTRY_ELIGIBILITY` (computed fresh), `ORDER_INTENT`,
`POSITION`. A latched study position now counts as current only if it is
**fresh** (`signal_max_age_bars`, default 3), **unfilled**, **inside the entry window**,
**not beyond the stop**, and **not beyond the chase limit**.

| | entry 100, stop 97.8, chase 103 | price 130 | price 90 |
|---|---|---|---|
| **Before** | `TRIGGER_CONFIRMED`, promoted to ready | `TRIGGER_CONFIRMED` | `TRIGGER_CONFIRMED` |
| **After** | `study_state=ACTIVE_STUDY_SIGNAL` retained | `EXTENDED_WAIT`, `ENTRY_EXPIRED` | `EXTENDED_WAIT`, `ENTRY_INVALIDATED` |

### F02 — bearish plans are now side-aware
Direction comes from the **qualifying condition**, never the latched direction, and
explicit `long_plan()` / `short_plan()` constructors own the level ordering.
Ambiguous simultaneous long+short evidence returns `BLOCKED_AMBIGUOUS` rather than guessing.

| bearish watch, ATR 2, put trigger 95, call trigger 105 | Before | After |
|---|---|---|
| trigger | 105 (call) | **95 (put)** |
| invalidation | 102.8 (below) | **97.2 (above)** |
| target | 109.4 (above) | **90.6 (below)** |
| chase limit | 108.0 (above) | **92.0 (below)** |
| direction | `None` | **SHORT** |

Mirrored long fixture verified independently: `target > trigger > invalidation`.

### F03 — extension is side-aware and acts as a veto
`_extension_state` tests `price > limit` for LONG and `price < limit` for SHORT, and its
second value is renamed to a genuine **price distance**.

| short, entry 100, ATR 2 | Before | After |
|---|---|---|
| chase limit | 103.0 (above entry) | **97.0 (below entry)** |
| price 90 extended? | `false` | **`true`** |
| second value | raw price delta | price distance |

### F04 — the browser no longer derives eligibility
- `ui.py` `state(row)` returned `EXECUTABLE` from score + source. It now returns
  `QUALIFIED_RESEARCH` — a **directional research label**, deliberately distinct from an
  execution label. The filter dropdown, chip CSS and verdict badge were updated to match.
- New **`src/qx/app/contracts.py`** (`candidate_contract_v1`) is the single authoritative
  shape for Discover / Explorer / Ideas / Notes / Workspace, exposed at **`/api/candidates`**.
  Its `execution` block is computed by calling the repository's own
  `OrderRouter.validate_execution_eligibility` and reports **`BLOCKED_RESEARCH_ONLY`**.

### F05 — FIFO keys on full contract identity
`_contract_key()` now returns the **option contract symbol** for matching, while
`_instrument_symbol()` remains the **reporting label** (underlying as a group dimension).

| open A −100, open B −500, close B +600 | Before | After |
|---|---|---|
| realized | **+500 (wrong)** | **+100 (correct)** |
| untouched lot A | consumed | **remains open under `OPTION:…C00100000`** |

### F15 — durable retry identity
Suppression keys on a **`request_id`** that survives **terminal** status; a MARKET fill no
longer escapes the guard. A deliberate repeat trade passes an explicit new `intent_id`.

| identical MARKET ticket ×2 | Before | After |
|---|---|---|
| records | **2 FILLED** | **1; second refused** |
| deliberate new intent | n/a | **allowed** |

---

## 4. Regression status — nothing broken

| Suite | Result |
|---|---|
| Phase A (new) | **20 / 20** |
| TOPS-MultiTrend | 29 / 29 |
| James Boyd 5 Phases | 31 / 31 |
| MASTER AUTO | 37 / 37 |
| Explorer service | 39 / 39 |
| Explorer HTTP | 32 / 32 |
| Ideas service | 39 / 39 |
| Ideas HTTP | 33 / 33 |
| Browser: explorer | 25 / 25 |
| Browser: trade ideas | 31 / 31 |
| Browser: full app | 61 / 61 |
| Browser: reports | 19 / 19 |
| Browser: context + settings | 20 / 20 |
| Embedded page scripts (`node --check`) | all valid |

**Changed files:** `src/qx/explorer/service.py`, `src/qx/app/ui.py`,
`src/qx/app/contracts.py` (new), `src/qx/app/server.py`, `src/qx/app/trade.py`,
`src/qx/reporting/pnl_engine.py`.

**Commands run:** `python scratch/verify_review_findings.py`,
`python scratch/test_phase_a.py`, `python scratch/audit_*.py`,
`node web/tests/qx-*.cjs`, `python scratch/audit_all_scripts.py`.

---

## 5. Constraints honoured

- No failed check was relabelled, no test weakened, no threshold moved to produce trades.
- Live execution stayed disabled; no order was placed with any broker.
- Study parity remains a separate layer; the original latched opinion is still reported.
- No claim of broker readiness, Thinkorswim parity, full-universe coverage or profitability.

---

## 6. Remaining work (unchanged from the review)

**Phase B:** F06 timestamps, F07 bar-selection, F08 timeframe propagation, F10 date-aligned
returns, F11 breadth denominators, F12 achievable pullback, F13 direction-conflict policy,
F18 membership, F21 coverage.
**Phase C:** F14 quote age, F16 typed risk validation, F17 accounting residuals and short
signs, F19 atomic storage, F24 server-bound intents, F25 service hardening.
**Phase D–F:** parity, structural targets, UI completeness, then evaluation — before any live
consideration.

**Two Phase A items I deliberately did not overreach on:** F17 (short-fallback sign and
unmatched partials) is Phase C because it needs broker field semantics confirmed rather than
a guessed convention; and F13's full conflict policy needs the Phase B direction contract to
land first. Both remain open and are *not* claimed fixed.
