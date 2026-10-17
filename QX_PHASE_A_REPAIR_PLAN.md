# QX Phase A — Repair Plan (Correctness Blockers)

Prepared in response to **QX_DEEP_CODE_REVIEW_DSH.md**. Live execution stays disabled throughout.

---

## 1. Verification result — the review is correct

I reproduced every finding I checked against the **current** code using the reviewer's own
cases plus additional probes (`scratch/verify_review_findings.py`):

| Finding | Verdict | Observed now |
|---|---|---|
| F01 chased latched signal → ready | **REPRODUCED** | `TRIGGER_CONFIRMED`, chase_limit 103, price 130, extension detected but bucket unchanged |
| F02 bearish watch uses call trigger | **REPRODUCED** | trigger 105 (put trigger is 95), stop 102.8 below, target 109.4 above |
| F03 short chase limit reversed | **REPRODUCED** | chase_limit 103 on a short; price 90 → `extended=false` |
| F04 browser-derived EXECUTABLE | **REPRODUCED** | `ui.py:163` `if(row.side && row.source==='schwab')return 'EXECUTABLE'` |
| F05 options FIFO conflation | **REPRODUCED** | reported +500, correct contract-level match +100 |
| F07 final completed bar dropped | **REPRODUCED** | input last 199 → output index 198 |
| F08 timeframe accepted, not applied | **REPRODUCED** | no `interval=` and no `minutes=` on the explore path |
| F09 stale snapshot still IDEAS_AVAILABLE | **REPRODUCED** | `stale:true, verdict:IDEAS_AVAILABLE, shown:1` |
| F11 breadth hides missing members | **REPRODUCED** | denominator 1, missing_data 0, weight covered 50% |
| F12 pullback view impossible | **REPRODUCED** | trend BULLISH ⇒ momentum BULLISH; view empty |
| F14 freshness checks provider name | **REPRODUCED** | `realtime:false` stub → READY_FOR_CONFIRMATION |
| F15 duplicate MARKET fills | **REPRODUCED** | two FILLED records |
| F16 negative limit passes presence | **REPRODUCED** | `limit_price` check passed, estimated_cost −1.0 |
| F16 missing equity passes concentration | **REPRODUCED** | `concentration_passed: true`, "equity unavailable" |
| F17a short fallback sign | **REPRODUCED** | −1900 where +100 expected |
| F17b partial close residual hidden | **REPRODUCED** | `partial:true`, `unmatched_closes: []` |

**16 / 16 checked findings reproduce.** I am not disputing any of them.

### I must also correct my own prior claim
My `QX_LOGIC_REVIEW.md` §9 stated *"`EXECUTABLE` appears nowhere."* That was true of the
**explorer path only**. F04 is right: the Discover results table still derives
`EXECUTABLE` in the browser from score + source. That claim was wrong and is now corrected
in memory.

### Why my own tests missed these
They encoded the same assumptions as the implementation. Two concrete examples:
- My breadth test asserted `denominator == 1` as **correct**, which is precisely the F11 defect.
- No explorer test ever exercised a **latched-but-chased** signal or a **bearish watch** plan,
  so F01/F02/F03 were structurally unreachable by my suite.

Both suites will gain the reviewer's edge cases as regression tests.

---

## 2. What is preserved (the reviewer's "worth preserving" list — I agree)

- Pure study modules, no logic trapped in the browser
- Explicit separate holdings / classified universes, no silent substitution
- Read-only account retrieval separated from simulated orders
- `OrderRouter` rejecting non-`VERIFIED` / non-`executable`
- Labelled simulations; the POST route calls `submit_simulated`
- Per-symbol failure isolation
- Deterministic, evidence-based notes
- **Existing provider timestamp/calendar contracts and the legacy regression suite — reused, not replaced**

---

## 3. Phase A scope — correctness blockers only

The reviewer's gate: *"all reproduced failures have regression tests that fail on the supplied
version and pass after fixes. No live orders."*

### A1 — Separate the state layers (fixes F01, F03, F13)
Introduce four distinct states where I currently conflate them:
```
STUDY_SIGNAL        the ported study's own latched opinion (research parity, unchanged)
ENTRY_ELIGIBILITY   current, actionable readiness — computed fresh, never inherited
ORDER_INTENT        a staged/simulated ticket
POSITION            an actual or simulated fill
```
`classify_entry` must stop promoting a latched historical trade. New readiness rules:
- require a signal on a **recent eligible bar** (declared `signal_max_age_bars`)
- require price **inside the entry window** (side-aware)
- reject if thesis invalidated (price beyond stop) or **expired**
- application of extension as a **veto**, not a flag

### A2 — Side-aware plan construction (fixes F02, F03)
- Determine proposed direction from the **qualifying condition**, not the latched direction.
- Explicit `long_plan()` / `short_plan()` constructors:
  - LONG: trigger < target, invalidation below, chase limit **above** entry
  - SHORT: trigger > target, invalidation **above**, chase limit **below** entry
- Ambiguous simultaneous long+short evidence ⇒ **blocked**, not silently resolved.
- Every branch returns a `direction`; `_extension_state` becomes side-aware and its second
  value renamed to what it is (price distance), with a real ATR distance alongside.

### A3 — Remove browser-derived eligibility (fixes F04)
- Delete `EXECUTABLE` from `ui.py state(row)`; the browser gets a **typed server candidate
  contract**.
- Keep directional score labels (`LONG / BUY CALL`) clearly distinct from execution labels.
- Add a frontend regression assertion covering **every** page, not only explorer rows.

### A4 — Contract-level FIFO identity (fixes F05)
- FIFO key becomes full **contract identity** (option symbol), with the underlying retained
  only as a reporting group.
- Explicit handling for assignments, expirations, exercises, transfers, corporate actions
  rather than treating them as ordinary closes.
- Acceptance: multiple expiries/strikes/call-put pairs reconcile at contract level.

### A5 — Durable retry identity (fixes F15)
- Duplicate suppression keyed on a **request-intent identity** that survives terminal status
  and restart, not on order status.
- Legitimate repeat trading uses an explicit **new intent id**.
- Atomic persistence so the guard cannot be bypassed by a partial write.

### A6 — Regression tests for every Phase A finding
Each of F01, F02, F03, F04, F05, F15 gets a test that **fails on the current code** and
passes after the fix, using the reviewer's exact fixtures.

---

## 4. Explicitly deferred to later phases

| Phase | Items |
|---|---|
| B | F06 timestamps, F07 bar selection, F08 timeframe propagation, F10 date-aligned returns, F11 breadth denominators, F12 achievable pullback, F13 direction conflict policy, F18 membership, F21 coverage |
| C | F14 quote age, F16 typed numeric/risk validation, F17 accounting residuals and short signs, F19 atomic storage, F24 server-bound intents, F25 service hardening |
| D | Thinkorswim parity, session VWAP, real structural targets, renamed proxies |
| E | UI completeness; keep unknown visibly unknown |
| F | Causal replay, costs, holdouts, ablation — **before** any live consideration |

---

## 5. Constraints I will honour

1. **No relabelling a failed check, weakening a test, or moving a threshold to produce more trades.**
2. Live execution **stays disabled**; no live order is authorized by the review or by me.
3. Study parity stays a **separate layer** from QX qualification; previous and new versions stay distinguishable.
4. No claim of broker readiness, Thinkorswim parity, full-universe coverage or profitability.
5. Every phase reports: changed files, commands run, test counts, fixtures, unresolved blockers, before/after examples.

---

## 6. Immediate next step

Implement **A1–A6** with the reviewer's fixtures as failing-first regression tests, report the
before/after evidence, and leave F06+ for Phase B.

**Decision requested:** proceed with Phase A as scoped above, or adjust scope/order first.
